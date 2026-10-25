# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "pedalboard", "soundfile", "pyloudnorm", "matplotlib", "numba"]
# ///
"""
make-trailer-audio-b.py - PecoFence trailer v3 soundtrack, variant B
"Warm melodic future pop" - 120 BPM, 4/4, A major, exactly 30.0 s.

Everything is synthesized in this file (numpy / scipy / numba DSP + a couple of
pedalboard effects). No samples, no soundfonts, no plugins, no voices. All
randomness comes from fixed seeds, so every run renders bit-identical audio.
The whole timeline (chords, sections, every SFX cue) is read from
src/trailer/cues.json.

Run (from anywhere):
    uv run --with numpy --with scipy --with pedalboard --with soundfile \
        --with pyloudnorm --with matplotlib --with numba python make-trailer-audio-b.py

Outputs (public/trailer-v3/audio/final/):
    soundtrack.wav   final master (music + sfx), 48 kHz / 24-bit / stereo, 1,440,000 samples
    music.wav        music stem at the master's pre-limiter gain
    sfx.wav          sfx stem at the master's pre-limiter gain
    spectrogram.png  mel spectrogram + cue lanes + short-term loudness
    chroma.png       chroma per chord segment against the expected chord
    report.json      loudness, true peak, onsets per cue, chord ranks, correlation, click scan

Layout of this file
    1. timeline      cues.json -> chord segments, sections, sfx cues
    2. theory        note names, chord table (voicings chosen for smooth voice leading)
    3. dsp           band-limited oscillators (polyBLEP at 2x), TPT state-variable filter,
                     Karplus-Strong, reverb IRs, delays, envelopes, sidechain curves
    4. instruments   FM tine e-piano, warm pad, soft pluck, sub + mid bass,
                     saw/square supersaw stabs, bright pluck lead, drum kit
    5. arrangement   parts per section (intro / brand / autosort / tabs / build / drop / end)
    6. sfx           every cue in cues.json
    7. mix + master  buses, sends, sidechain, cue ducking, LF mono, TP limiter, -14 LUFS
    8. analysis      report.json + the two diagnostic plots
"""

from __future__ import annotations

import json
import math
import pathlib
import time

import numpy as np
import pedalboard as pb
import pyloudnorm as pyln
import soundfile as sf
from numba import njit
from scipy import signal

# =============================================================================
# 1. TIMELINE
# =============================================================================

SR = 48000                  # output rate
OS = 2                      # oversampling factor for the saw/square/FM voices
SR2 = SR * OS
N = 1_440_000               # exactly 30.0 s
DUR = N / SR

HERE = pathlib.Path(__file__).resolve()
PROMO = HERE.parents[1]
CUES_PATH = PROMO / "src" / "trailer" / "cues.json"
OUT_DIR = PROMO / "public" / "trailer-v3" / "audio" / "final"

CUES = json.loads(CUES_PATH.read_text(encoding="utf-8"))
BPM = float(CUES["bpm"])
BEAT = 60.0 / BPM           # 0.5 s
BAR = 4 * BEAT              # 2.0 s
S16 = BEAT / 4              # 0.125 s
assert abs(float(CUES["duration"]) - DUR) < 1e-9

SECTIONS = [(s["name"], float(s["start"]), float(s["end"])) for s in CUES["sections"]]
SEC = {name: (a, b) for name, a, b in SECTIONS}
SFX = CUES["sfx"]

GAP_START = 19.94           # tiny silence before the drop (cues: optional 19.94-20.0)
DROP = 20.0
FADE_START = 27.6
FADE_END = 29.8             # digital silence from here on

LAND_TIMES = [c["t"] for c in SFX if c["type"] == "land"]


def bar_t(bar: int) -> float:
    """Start time of a 1-based bar."""
    return (bar - 1) * BAR


def chord_segments():
    """Chord per bar, with the 'then' half-bar changes split out."""
    out = []
    ch = CUES["chords"]
    for i, c in enumerate(ch):
        end = float(ch[i + 1]["t"]) if i + 1 < len(ch) else DUR
        name = c["chord"].split(" ")[0]          # "Aadd9 (ring out)" -> "Aadd9"
        if "then" in c:
            mid = float(c["then"]["t"])
            out.append(dict(t0=float(c["t"]), t1=mid, chord=name, bar=c["bar"]))
            out.append(dict(t0=mid, t1=end, chord=c["then"]["chord"], bar=c["bar"]))
        else:
            out.append(dict(t0=float(c["t"]), t1=end, chord=name, bar=c["bar"]))
    return out


SEGS = chord_segments()


def merged_segments():
    """Consecutive identical chords merged (sustained instruments)."""
    out = []
    for s in SEGS:
        if out and out[-1]["chord"] == s["chord"]:
            out[-1] = dict(out[-1], t1=s["t1"])
        else:
            out.append(dict(s))
    return out


def chord_at(t: float) -> str:
    for s in SEGS:
        if s["t0"] - 1e-9 <= t < s["t1"] - 1e-9:
            return s["chord"]
    return SEGS[-1]["chord"]


# =============================================================================
# 2. THEORY
# =============================================================================

PCS = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6,
       "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
PC_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi(name: str) -> int:
    i = 2 if len(name) > 2 and name[1] in "#b" else 1
    return 12 * (int(name[i:]) + 1) + PCS[name[:i]]


def hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def cents(c: float) -> float:
    return 2.0 ** (c / 1200.0)


# Interval sets for chord templates (root = 0).
QUAL = {"maj": [0, 4, 7], "min": [0, 3, 7], "m7": [0, 3, 7, 10], "m9": [0, 3, 7, 10, 2],
        "maj9": [0, 4, 7, 11, 2], "sus4": [0, 5, 7], "add9": [0, 4, 7, 2]}

# Voicings. Pad voicings voice-lead by step between neighbours:
#   F#m9 [F#3 A3 C#4 E4 G#4] -> Esus4 [E3 A3 B3 E4 A4] -> E [E3 G#3 B3 E4 G#4]
#   -> Dmaj9 [D3 A3 C#4 E4 F#4] -> A/C# [E3 A3 C#4 E4 A4] -> F#m7 [F#3 A3 C#4 E4 F#4]
#   -> Aadd9 [E3 A3 C#4 E4 B4]
# Stabs (drop) sit an octave up with the root/bass tone at the bottom.
CHORDS = {
    "F#m9": dict(root="F#", q="m9", bass="F#",
                 pad=["F#3", "A3", "C#4", "E4", "G#4"], arp=["F#4", "A4", "C#5", "E5", "G#5"],
                 stab=["F#4", "A4", "C#5", "E5", "G#5"]),
    "Esus4": dict(root="E", q="sus4", bass="E",
                  pad=["E3", "A3", "B3", "E4", "A4"], arp=["B3", "E4", "A4", "B4", "E5"],
                  stab=["B3", "E4", "A4", "B4", "E5"]),
    "E": dict(root="E", q="maj", bass="E",
              pad=["E3", "G#3", "B3", "E4", "G#4"], arp=["B3", "E4", "G#4", "B4", "E5"],
              stab=["B3", "E4", "G#4", "B4", "E5"]),
    "Dmaj9": dict(root="D", q="maj9", bass="D",
                  pad=["D3", "A3", "C#4", "E4", "F#4"], arp=["D4", "A4", "C#5", "E5", "F#5"],
                  stab=["D4", "F#4", "A4", "C#5", "E5"]),
    "A/C#": dict(root="A", q="maj", bass="C#",
                 pad=["E3", "A3", "C#4", "E4", "A4"], arp=["A3", "E4", "A4", "C#5", "E5"],
                 stab=["C#4", "E4", "A4", "E5", "A5"]),
    "F#m7": dict(root="F#", q="m7", bass="F#",
                 pad=["F#3", "A3", "C#4", "E4", "F#4"], arp=["C#4", "F#4", "A4", "C#5", "E5"],
                 stab=["C#4", "F#4", "A4", "C#5", "E5"]),
    "Aadd9": dict(root="A", q="add9", bass="A",
                  pad=["E3", "A3", "C#4", "E4", "B4"], arp=["A4", "B4", "C#5", "E5", "A5"],
                  stab=["C#4", "E4", "A4", "B4", "E5"]),
}


def voicing(chord: str, part: str):
    return [midi(n) for n in CHORDS[chord][part]]


def bass_midi(chord: str) -> int:
    """Mid-bass note in octave 2 (C#2..A2); the sub plays an octave lower."""
    return midi(CHORDS[chord]["bass"] + "2")


def chord_tone_names(chord: str):
    c = CHORDS[chord]
    r = PCS[c["root"]]
    return [PC_NAMES[(r + i) % 12] for i in QUAL[c["q"]]]


# =============================================================================
# 3. DSP PRIMITIVES
# =============================================================================

def _t(n: int, sr: int = SR) -> np.ndarray:
    return np.arange(n) / sr


# --- band-limited oscillators (polyBLEP; rendered at SR2 and decimated) -------

def _polyblep(ph, dt):
    out = np.zeros_like(ph)
    m = ph < dt
    x = ph[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m = ph > 1.0 - dt
    x = (ph[m] - 1.0) / dt[m]
    out[m] = x * x + x + x + 1.0
    return out


def _phase(freq, n, sr, phase0):
    f = np.ascontiguousarray(np.broadcast_to(np.asarray(freq, dtype=np.float64), (n,)))
    dt = f / sr
    ph = (phase0 + np.concatenate(([0.0], np.cumsum(dt[:-1])))) % 1.0
    return ph, dt


def saw(freq, n, sr=SR2, phase0=0.0):
    ph, dt = _phase(freq, n, sr, phase0)
    return 2.0 * ph - 1.0 - _polyblep(ph, dt)


def square(freq, n, sr=SR2, phase0=0.0):
    ph, dt = _phase(freq, n, sr, phase0)
    y = np.where(ph < 0.5, 1.0, -1.0)
    return y + _polyblep(ph, dt) - _polyblep((ph + 0.5) % 1.0, dt)


def sine(freq, n, sr=SR, phase0=0.0):
    ph, _ = _phase(freq, n, sr, phase0)
    return np.sin(2.0 * np.pi * ph)


_DECIM = signal.firwin(191, 21500, fs=SR2, window=("kaiser", 8.6))


def down(x):
    """SR2 -> SR with a steep linear-phase FIR (stopband > ~23 kHz)."""
    return signal.resample_poly(x, 1, OS, axis=-1, window=_DECIM)


# --- filters ------------------------------------------------------------------

@njit(cache=False)
def _svf_core(x, fc, q, mode, sr):
    # Zavalishin TPT state-variable filter with per-sample cutoff.
    n = x.shape[0]
    y = np.empty(n)
    ic1 = 0.0
    ic2 = 0.0
    k = 1.0 / q
    fmax = 0.45 * sr
    for i in range(n):
        f = fc[i]
        if f > fmax:
            f = fmax
        if f < 5.0:
            f = 5.0
        g = math.tan(math.pi * f / sr)
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        if mode == 0:
            y[i] = v2
        elif mode == 1:
            y[i] = k * v1
        else:
            y[i] = x[i] - k * v1 - v2
    return y


def svf(x, fc, q=0.707, mode="lp", sr=SR):
    m = {"lp": 0, "bp": 1, "hp": 2}[mode]
    x = np.asarray(x, dtype=np.float64)
    fcv = np.ascontiguousarray(np.broadcast_to(np.asarray(fc, dtype=np.float64), x.shape[-1:]))
    if x.ndim == 1:
        return _svf_core(np.ascontiguousarray(x), fcv, float(q), m, float(sr))
    return np.stack([_svf_core(np.ascontiguousarray(ch), fcv, float(q), m, float(sr)) for ch in x])


_SOS = {}


def filt(x, kind, f, order=2, sr=SR):
    key = (kind, tuple(np.atleast_1d(f).tolist()), order, sr)
    if key not in _SOS:
        _SOS[key] = signal.butter(order, f, btype=kind, fs=sr, output="sos")
    return signal.sosfilt(_SOS[key], x, axis=-1)


# --- Karplus-Strong (soft organic pluck) ---------------------------------------

@njit(cache=False)
def _ks_core(exc, period, n, g, damp):
    y = np.zeros(n)
    ne = exc.shape[0]
    for i in range(n):
        v = exc[i] if i < ne else 0.0
        d = i - period
        if d >= 1.0:
            j = int(d)
            fr = d - j
            a = (1.0 - fr) * y[j] + fr * y[j + 1]
            b = (1.0 - fr) * y[j - 1] + fr * y[j] if j >= 1 else y[j]
            v += g * ((1.0 - damp) * a + damp * 0.5 * (a + b))
        y[i] = v
    return y


# --- envelopes / helpers --------------------------------------------------------

def release_env(n, sr, gate, rel):
    """1 until gate, raised-cosine to 0 over rel."""
    t = _t(n, sr)
    x = np.clip((t - gate) / max(rel, 1e-4), 0.0, 1.0)
    return 0.5 * (1.0 + np.cos(np.pi * x))


def attack_env(n, sr, att):
    t = _t(n, sr)
    x = np.clip(t / max(att, 1e-5), 0.0, 1.0)
    return 0.5 * (1.0 - np.cos(np.pi * x))


def tail_fade(x, sec=0.01, sr=SR):
    k = min(int(sec * sr), x.shape[-1])
    if k > 0:
        x[..., -k:] *= np.linspace(1.0, 0.0, k)
    return x


def st_noise(rng, n, corr=0.75):
    """Stereo noise with L/R correlation ~corr (mono-safe width for sweeps and cymbals)."""
    c = rng.standard_normal(n)
    return math.sqrt(corr) * c + math.sqrt(1 - corr) * rng.standard_normal((2, n))


def pan_gains(p):
    th = (np.clip(p, -1, 1) + 1.0) * np.pi / 4.0
    return np.cos(th) * math.sqrt(2.0), np.sin(th) * math.sqrt(2.0)


def to_stereo(x, pan=0.0):
    if x.ndim == 2:
        return x
    gl, gr = pan_gains(pan)
    return np.stack([x * gl, x * gr])


def curve(points, log=False):
    """Piecewise-linear (or log-linear) automation over the full timeline."""
    t = _t(N)
    ts = np.array([p[0] for p in points], dtype=float)
    vs = np.array([p[1] for p in points], dtype=float)
    if log:
        return np.exp(np.interp(t, ts, np.log(vs)))
    return np.interp(t, ts, vs)


def duck_curve(times, depth, attack=0.004, hold=0.012, release=0.2):
    """Gain curve dipping to (1-depth) at each time (sidechain / cue ducking)."""
    g = np.ones(N)
    na = max(int(attack * SR), 1)
    nh = int(hold * SR)
    nr = max(int(release * SR), 1)
    xa = np.arange(na) / na
    xr = np.arange(nr) / nr
    shape = np.concatenate([1.0 - depth * 0.5 * (1.0 - np.cos(np.pi * xa)),
                            np.full(nh, 1.0 - depth),
                            1.0 - depth * (1.0 - xr * xr * (3.0 - 2.0 * xr))])
    for tk in times:
        i0 = int(round(tk * SR)) - na
        a, b = max(i0, 0), min(i0 + shape.size, N)
        if b > a:
            g[a:b] = np.minimum(g[a:b], shape[a - i0:b - i0])
    return g


def db(x):
    return 10.0 ** (x / 20.0)


# --- reverb (synthetic stereo impulse responses, convolution) -------------------

def make_ir(seconds, rt60, seed, predelay=0.012, band_mult=(1.25, 1.0, 0.72, 0.45),
            corr=0.35, early=True):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = _t(n)
    edges = [("lowpass", 450), ("bandpass", [450, 1900]), ("bandpass", [1900, 6500]),
             ("highpass", 6500)]
    common = rng.standard_normal(n)
    ir = np.zeros((2, n))
    for ch in range(2):
        nz = math.sqrt(1 - corr) * rng.standard_normal(n) + math.sqrt(corr) * common
        out = np.zeros(n)
        for (kind, f), mult in zip(edges, band_mult):
            out += filt(nz, kind, f, 2) * np.exp(-6.9078 * t / (rt60 * mult))
        out *= 1.0 - np.exp(-t / 0.015)                 # diffusion build-up
        ir[ch] = out
    if early:                                          # a few early reflections
        for k in range(10):
            d = int(rng.uniform(0.004, 0.045) * SR)
            ch = k % 2
            ir[ch, d] += rng.uniform(0.6, 1.6) * (1 if rng.random() < 0.5 else -1) * 8.0
    pd = int(predelay * SR)
    ir = np.concatenate([np.zeros((2, pd)), ir], axis=1)
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
    ir *= np.linspace(1, 0, ir.shape[1]) ** 0.25        # guarantee a clean end
    return ir


def convolve_st(x, ir):
    if not np.any(x):
        return np.zeros_like(x)
    return np.stack([signal.oaconvolve(x[c], ir[c])[:N] for c in range(2)])


def tap_delay(x, dt, fb, taps, spread=0.9, lp=5500, hp=300, pingpong=True):
    """Filtered multi-tap echo (feedback approximated by progressively filtered taps)."""
    out = np.zeros_like(x)
    cur = filt(0.5 * (x[0] + x[1]), "highpass", hp, 1)
    d = int(round(dt * SR))
    for k in range(1, taps + 1):
        cur = filt(cur, "lowpass", lp, 1)
        if k * d >= N:
            break
        sh = np.zeros(N)
        sh[k * d:] = cur[:N - k * d]
        p = (-spread if k % 2 == 1 else spread) if pingpong else 0.0
        gl, gr = pan_gains(p)
        out[0] += fb ** (k - 1) * gl * sh
        out[1] += fb ** (k - 1) * gr * sh
    return out


def chorus(x, rate=0.5, depth=0.25, delay_ms=9.0, mix=0.35):
    board = pb.Pedalboard([pb.Chorus(rate_hz=rate, depth=depth, centre_delay_ms=delay_ms,
                                     feedback=0.0, mix=mix)])
    return board(x.astype(np.float32), SR).astype(np.float64)


# --- pre/post-drop buses ---------------------------------------------------------
# Every event lands either in the "pre" layer (starts before the drop) or the "post"
# layer. Each layer is processed separately (filters, delays, reverbs) and the pre
# layer is faded out at 19.94 s, so the 60 ms gap before the drop is really empty
# and no reverb tail can be switched back on at 20.0.

PRE_GATE = np.ones(N)
_g0 = int(round((GAP_START - 0.006) * SR))
_g1 = int(round(GAP_START * SR))
PRE_GATE[_g0:_g1] = 0.5 * (1 + np.cos(np.pi * np.arange(_g1 - _g0) / (_g1 - _g0)))
PRE_GATE[_g1:] = 0.0


class Bus:
    def __init__(self, name):
        self.name = name
        self.pre = np.zeros((2, N))
        self.post = np.zeros((2, N))
        self.onsets = []

    def add(self, x, t0, gain=1.0, pan=0.0, part=None):
        x = to_stereo(np.asarray(x, dtype=np.float64), pan)
        i0 = int(round(t0 * SR))
        if part is None:
            part = "post" if t0 >= DROP - 1e-6 else "pre"
        buf = self.post if part == "post" else self.pre
        a, b = max(i0, 0), min(i0 + x.shape[1], N)
        if b > a:
            buf[:, a:b] += gain * x[:, a - i0:b - i0]
        self.onsets.append(t0)

    def map(self, fn):
        self.pre = fn(self.pre)
        self.post = fn(self.post)
        return self

    def gain(self, g):
        self.pre = self.pre * g
        self.post = self.post * g
        return self

    def send_to(self, other, level):
        other.pre += self.pre * level
        other.post += self.post * level

    def mix(self):
        return self.pre * PRE_GATE + self.post


# =============================================================================
# 4. INSTRUMENTS
# =============================================================================

def ep_note(mn, gate, vel, rel=0.35, tine=1.0):
    """FM tine electric piano (DX-style: 1:1 body pair + 1:14 tine pair), rendered at 2x.
    Mono on purpose (no L/R detune, which would comb-filter in mono); width comes from the
    bus tremolo/autopan and chorus."""
    f = hz(mn)
    n = int((gate + rel + 0.02) * SR2)
    t = _t(n, SR2)
    kscale = 2.0 ** (-(mn - 60) / 24.0)
    tau = 1.7 * kscale
    amp = (0.3 * np.exp(-t / 0.09) + 0.7 * np.exp(-t / tau)) * (1.0 - np.exp(-t / 0.0009))
    w = 2.0 * np.pi * f * t
    ib = vel * (1.4 * np.exp(-t / 0.22) + 0.28)
    body = np.sin(w + ib * np.sin(w))
    it = (0.5 + 1.7 * vel) * np.exp(-t / 0.011)
    tn = np.sin(w + it * np.sin(14.0 * w)) * np.exp(-t / 0.3)
    x = (0.8 * body + 0.28 * tine * tn) * amp * (vel ** 1.2) * release_env(n, SR2, gate, rel)
    x = np.tanh(1.3 * x) / np.tanh(1.3)
    return down(x)


def pad_chord(notes, gate, att, rel, rng, width=6.0):
    """Warm pad: three detuned saws + a sine per note, slow drift. The detuned saws are
    *panned* (each is present in both channels at different levels) rather than being
    separate L/R oscillators, so the pad stays mono-compatible. Bus LPF shapes it."""
    n = int((gate + rel + 0.01) * SR2)
    t = _t(n, SR2)
    L = np.zeros(n)
    R = np.zeros(n)
    for i, mn in enumerate(notes):
        f = hz(mn)
        drift = 1.0 + 0.0011 * np.sin(2 * np.pi * (0.13 + 0.04 * i) * t + rng.uniform(0, 6.28))
        fd = f * drift
        sn = sine(fd, n, SR2, rng.random())
        L += 0.45 * sn
        R += 0.45 * sn
        for dc, p in ((-width, -0.45), (0.0, 0.0), (width, 0.45)):
            s = saw(fd * cents(dc), n, SR2, rng.random()) * 0.42
            gl, gr = pan_gains(p)
            L += gl * s
            R += gr * s
    env = attack_env(n, SR2, att) * release_env(n, SR2, gate, rel)
    x = np.stack([L, R]) * env / math.sqrt(len(notes))
    return down(x)


def ks_pluck(mn, gate, vel, rng, t60=1.0, bright=0.5, damp=0.5, rel=0.06, sine_mix=0.25):
    """Karplus-Strong soft pluck + a sine fundamental for warmth (mono, SR)."""
    f = hz(mn)
    P = SR / f - 0.5 * damp
    Lx = max(8, int(P))
    ex = rng.standard_normal(Lx)
    a = float(np.clip(1.0 - bright, 0.0, 0.95))
    ex = signal.lfilter([1.0 - a], [1.0, -a], ex)
    ex -= ex.mean()
    ex *= np.sin(np.pi * (np.arange(Lx) + 0.5) / Lx)
    n = int((gate + rel + 0.005) * SR)
    g = 0.001 ** (1.0 / (t60 * f))
    y = _ks_core(np.ascontiguousarray(ex), float(P), n, float(g), float(damp))
    y /= np.max(np.abs(y)) + 1e-12
    t = _t(n)
    y += sine_mix * np.sin(2 * np.pi * f * t) * np.exp(-t / (t60 * 0.35)) * (1 - np.exp(-t / 0.002))
    y = filt(y, "highpass", 40, 1)
    return y * release_env(n, SR, gate, rel) * vel


def bass_mid_note(mn, gate, vel, rel=0.05, bright=1.0):
    """Mid bass layer: saw + square, envelope-swept low-pass, gentle drive (2x)."""
    f = hz(mn)
    n = int((gate + rel + 0.01) * SR2)
    t = _t(n, SR2)
    x = 0.65 * saw(f, n, SR2, 0.0) + 0.35 * square(f * cents(-5), n, SR2, 0.25)
    fc = 330.0 + 1300.0 * bright * vel * np.exp(-t / 0.05)
    x = svf(x, fc, 0.9, "lp", SR2)
    x = np.tanh(2.0 * x) / np.tanh(2.0)
    x = filt(x, "lowpass", 2200, 2, sr=SR2)
    env = np.minimum(t / 0.004, 1.0) * (0.78 + 0.22 * np.exp(-t / 0.25))
    return down(x * env * release_env(n, SR2, gate, rel)) * vel


def sub_note(mn, gate, rel=0.06, att=0.006):
    f = hz(mn)
    n = int((gate + rel + 0.01) * SR)
    x = sine(f, n, SR, 0.0)
    x = np.tanh(1.5 * x) / np.tanh(1.5)            # a little 3rd harmonic for small speakers
    return x * attack_env(n, SR, att) * release_env(n, SR, gate, rel)


def stab_chord(notes, gate, vel, rng, fc_lo=1300.0, fc_hi=3300.0, tau=0.12, rel=0.09, att=0.003):
    """Future-pop chord stab: 7 detuned voices per note (5 saw + 2 square), wide, LPF env."""
    n = int((gate + rel + 0.01) * SR2)
    t = _t(n, SR2)
    L = np.zeros(n)
    R = np.zeros(n)
    det = [-17, -10, -4, 0, 4, 10, 17]
    pans = [-0.9, 0.55, -0.3, 0.0, 0.3, -0.55, 0.9]
    kinds = ["saw", "sq", "saw", "saw", "saw", "sq", "saw"]
    for mn in notes:
        f = hz(mn)
        for d, p, k in zip(det, pans, kinds):
            osc = saw(f * cents(d), n, SR2, rng.random()) if k == "saw" else \
                0.55 * square(f * cents(d), n, SR2, rng.random())
            gl, gr = pan_gains(p)
            L += gl * osc
            R += gr * osc
    fc = fc_lo + (fc_hi - fc_lo) * vel * np.exp(-t / tau)
    x = svf(np.stack([L, R]), fc, 0.75, "lp", SR2)
    env = attack_env(n, SR2, att) * (0.8 + 0.2 * np.exp(-t / 0.3)) * release_env(n, SR2, gate, rel)
    x = x * env / (len(notes) * math.sqrt(7.0))
    x = np.tanh(1.4 * x) / np.tanh(1.4)
    return down(x) * vel


def lead_note(mn, gate, vel, rng, rel=0.12):
    """Bright pluck lead: 2 detuned saws + sub-octave square, snappy LPF env, glass partial."""
    f = hz(mn)
    n = int((gate + rel + 0.01) * SR2)
    t = _t(n, SR2)
    x = 0.5 * saw(f * cents(-8), n, SR2, rng.random()) + 0.5 * saw(f * cents(8), n, SR2, rng.random())
    x += 0.28 * square(f * 0.5, n, SR2, rng.random())
    fc = 1400.0 + 6500.0 * vel * np.exp(-t / 0.085)
    x = svf(x, fc, 0.85, "lp", SR2)
    x += 0.16 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.12)
    env = np.minimum(t / 0.002, 1.0) * (0.35 + 0.65 * np.exp(-t / 0.22))
    return down(x * env * release_env(n, SR2, gate, rel)) * vel


# --- drums (SR; noise + sines, no aliasing concerns) ---------------------------

def kick(rng, vel=1.0, tone=51.0, decay=0.30):
    """Round, deep kick: pitch-swept sine + soft beater click, gentle saturation."""
    n = int(0.7 * SR)
    t = _t(n)
    f = tone + 120.0 * np.exp(-t / 0.030) + 40.0 * np.exp(-t / 0.004)
    ph = 2 * np.pi * np.concatenate(([0.0], np.cumsum(f[:-1]))) / SR
    body = np.sin(ph) * np.exp(-t / decay) * (1 - np.exp(-t / 0.0005))
    nz = filt(rng.standard_normal(n), "highpass", 3000) * np.exp(-t / 0.0010) * 0.10
    tick = np.sin(2 * np.pi * 1500 * t) * np.exp(-t / 0.0022) * 0.07
    x = np.tanh(1.8 * (body + nz + tick)) / np.tanh(1.8)
    return tail_fade(x, 0.03) * vel


def clap(rng, vel=1.0):
    n = int(0.45 * SR)
    t = _t(n)
    common = rng.standard_normal(n)
    nz = 0.8 * common + 0.6 * rng.standard_normal((2, n))
    band = filt(nz, "bandpass", [900, 3200], 2)
    env = np.zeros(n)
    for k, o in enumerate([0.0, 0.0095, 0.0185, 0.0275]):
        env += (t >= o) * np.exp(-np.maximum(t - o, 0) / 0.004) * (0.8 + 0.2 * k / 3)
    env += (t >= 0.0275) * np.exp(-np.maximum(t - 0.0275, 0) / 0.12) * 0.55
    return tail_fade(band * env, 0.02) * vel


def rim(rng, vel=1.0):
    n = int(0.12 * SR)
    t = _t(n)
    x = 0.6 * np.sin(2 * np.pi * 1720 * t) * np.exp(-t / 0.010)
    x += 0.45 * np.sin(2 * np.pi * 480 * t) * np.exp(-t / 0.016)
    x += 0.35 * filt(rng.standard_normal(n), "highpass", 4000) * np.exp(-t / 0.0012)
    return tail_fade(x * (1 - np.exp(-t / 0.0002)), 0.01) * vel


def snare(rng, vel=1.0, tune=1.0, decay=0.15, body=1.0):
    n = int(0.5 * SR)
    t = _t(n)
    f = 190.0 * tune * (1 + 0.25 * np.exp(-t / 0.01))
    ph = 2 * np.pi * np.concatenate(([0.0], np.cumsum(f[:-1]))) / SR
    b = (np.sin(ph) * np.exp(-t / 0.06) + 0.4 * np.sin(1.6 * ph) * np.exp(-t / 0.04)) * body
    nz = filt(rng.standard_normal(n), "bandpass", [1500, 9000]) * np.exp(-t / decay)
    x = (0.55 * b + 0.8 * nz) * (1 - np.exp(-t / 0.0003))
    return tail_fade(x, 0.02) * vel


def hat(rng, vel=1.0, open_=False):
    n = int((0.5 if open_ else 0.09) * SR)
    t = _t(n)
    nz = rng.standard_normal(n)
    x = filt(nz, "highpass", 7000, 4) + 0.5 * filt(nz, "bandpass", [9500, 12500], 2)
    env = np.exp(-t / (0.15 if open_ else 0.018)) * (1 - np.exp(-t / 0.0003))
    return tail_fade(x * env, 0.01) * vel


def shaker(rng, vel=1.0):
    n = int(0.12 * SR)
    t = _t(n)
    x = filt(rng.standard_normal(n), "bandpass", [4500, 11000], 2)
    env = (1 - np.exp(-t / 0.004)) * np.exp(-t / 0.035)
    return tail_fade(x * env, 0.01) * vel


def crash(rng, vel=1.0, dur=2.8):
    n = int(dur * SR)
    t = _t(n)
    x = filt(st_noise(rng, n, 0.6), "highpass", 3500, 2)
    for _k in range(14):
        fr = rng.uniform(3000, 11000)
        tone = 0.08 * np.sin(2 * np.pi * fr * t + rng.uniform(0, 6.28)) * np.exp(-t / rng.uniform(0.4, 1.2))
        x += to_stereo(tone, rng.uniform(-0.5, 0.5))
    x = x * np.exp(-t / 0.8) * (1 - np.exp(-t / 0.0008))
    return tail_fade(x, 0.2) * vel


# =============================================================================
# 5. ARRANGEMENT
# =============================================================================

# Intro motif (e-piano): five notes, dotted rhythm. The drop hook develops it
# (same rhythm, transposed up a 4th, then extended and answered).
MOTIF_BEATS = [0.0, 0.75, 1.5, 2.0, 3.0]
MOTIF = ["C#5", "E5", "F#5", "E5", "B4"]
MOTIF_LEN = [0.6, 0.6, 0.45, 0.9, 0.9]
ANSWER_BEATS = [0.0, 0.75, 1.5, 2.0]
ANSWER = ["B4", "E5", "F#5", "A5"]
ANSWER_LEN = [0.6, 0.6, 0.45, 1.9]

# Drop lead hook: (bar, beat, note, length in beats, velocity)
HOOK = [
    (11, 0.0, "F#5", 0.5, 1.0), (11, 0.75, "A5", 0.5, 0.85), (11, 1.5, "B5", 0.45, 0.9),
    (11, 2.0, "A5", 0.75, 0.9), (11, 3.0, "E5", 0.5, 0.85), (11, 3.5, "F#5", 0.45, 0.75),
    (12, 0.0, "E5", 0.5, 0.95), (12, 0.75, "A5", 0.5, 0.85), (12, 1.5, "B5", 0.45, 0.9),
    (12, 2.0, "C#6", 0.75, 1.0), (12, 3.0, "B5", 0.5, 0.85), (12, 3.5, "A5", 0.45, 0.75),
    (13, 0.0, "A5", 0.5, 0.95), (13, 0.75, "F#5", 0.5, 0.85), (13, 1.5, "E5", 0.45, 0.85),
    (13, 2.0, "G#5", 0.75, 0.95), (13, 3.0, "B5", 0.5, 1.0),
]

ARP8 = [0, 2, 4, 1, 3, 2, 4, 3]                     # 8th-note arp shape over 5 chord tones
ARP16 = [0, 2, 4, 2, 1, 3, 4, 3, 0, 2, 4, 3, 1, 3, 4, 2]
BASS_GROOVE = [(0, 3.5), (6, 1.5), (8, 3.0), (11, 2.0), (14, 1.5)]      # (16th step, len)
DROP_RHYTHM = [(0, 2.0), (3, 2.0), (6, 3.0), (10, 2.0), (13, 2.0)]      # 3-3-4-3-3 stabs
DROP_VEL = [1.0, 0.8, 0.9, 0.85, 0.8]


# Section faders in dB: the energy map of cues.json (intro 0.25 < build 0.45 < brand 0.7 <
# autosort 0.75 < tabs 0.8 < drop 1.0; end 0.35) realised as per-bus levels.
_S = [s[0] for s in SECTIONS]


def _row(*vals):
    return dict(zip(_S, vals))


#                 intro  brand  autos  tabs   build  drop   end
MIX_DB = {
    "pad":   _row(-8.5, -10.4, -9.0, -9.0, -4.6, -8.8, -9.9),
    "ep":    _row(-9.0, -8.9, -5.6, -7.0, -5.2, -6.8, -9.6),
    "arp":   _row(-1.0, -1.0, 0.5, 0.0, 1.2, 0.5, 0.5),
    "sub":   _row(-7.0, -7.0, -7.0, -5.6, -5.6, -4.2, -14.0),
    "bass":  _row(-9.4, -9.4, -8.6, -8.5, -8.5, -5.2, -10.8),
    "stab":  _row(2.6, 2.6, 2.6, 2.6, 2.6, 2.6, -4.2),
    "lead":  _row(-4.6, -4.6, -4.6, -4.6, -4.6, -4.6, -4.6),
    "kick":  _row(-7.2, -7.2, -5.0, -3.8, -3.8, -3.2, -3.2),
    "drums": _row(-5.0, -5.0, -2.0, -1.0, -1.0, -2.0, -2.0),
}
RETURN_DB = {
    "hall":  _row(-6.0, -6.0, -6.0, -6.0, -5.5, -4.5, -5.0),
    "plate": _row(-8.0, -8.0, -8.0, -8.0, -8.0, -8.0, -8.0),
    "room":  _row(-10.5, -10.5, -10.5, -10.5, -10.5, -10.5, -10.5),
}


def section_gain(table, ramp=0.03):
    """Per-section level curve; each change ramps over the last 30 ms before a boundary."""
    pts = []
    for name, a, b in SECTIONS:
        v = db(table[name])
        pts += [(a, v), (b - ramp, v)]
    pts[-1] = (SECTIONS[-1][2], pts[-1][1])
    return curve(pts)


def near_land(t, tol=0.03):
    return any(abs(t - lt) < tol for lt in LAND_TIMES)


UI_TIMES = [c["t"] for c in SFX if c["type"] in ("click", "snap", "tick")]


def near_ui(t, tol=0.025):
    """Carving: percussion/arp notes that would sit on top of a UI cue are left out."""
    return any(abs(t - u) < tol for u in UI_TIMES)


def compose_music():
    rng = np.random.default_rng(20260926)
    B = {k: Bus(k) for k in ["pad", "ep", "arp", "sub", "bass", "stab", "lead", "kick", "drums"]}
    kicks = []

    # ---------------- pad (whole piece; filtered intro, pumping later) ----------
    for seg in merged_segments():
        name, t0, t1 = seg["chord"], seg["t0"], seg["t1"]
        att = 1.4 if t0 == 0 else (0.05 if t0 in (4.0, 20.0, 26.0) else 0.22)
        gate, rel = min(t1, FADE_END) - t0, 0.45
        if t0 < DROP <= t1 - 1e-9:
            gate = GAP_START - t0
        if t0 >= SEC["end"][0]:
            gate, rel = 1.6, 2.0
        B["pad"].add(pad_chord(voicing(name, "pad"), gate, att, rel, rng), t0)

    # ---------------- e-piano -----------------------------------------------
    def ep_chord(notes, t0, gate, vel, rel=0.4, roll=0.004):
        for i, mn in enumerate(notes):
            B["ep"].add(ep_note(mn, gate, vel * rng.uniform(0.92, 1.0), rel), t0 + i * roll,
                        pan=rng.uniform(-0.15, 0.15))

    def ep_line(notes, beats, lens, t_bar, vel):
        for nm, b, ln in zip(notes, beats, lens):
            B["ep"].add(ep_note(midi(nm), ln * BEAT, vel * rng.uniform(0.9, 1.0), 0.5), t_bar + b * BEAT)

    top4 = lambda ch: voicing(ch, "pad")[1:]
    # intro (bars 1-2): soft left-hand chords + the motif and its answer
    ep_chord([midi("F#2"), midi("E3"), midi("A3"), midi("C#4")], 0.0, 1.9, 0.34, roll=0.012)
    ep_chord([midi("E2"), midi("B2"), midi("A3")], 2.0, 1.4, 0.32, roll=0.012)
    ep_line(MOTIF, MOTIF_BEATS, MOTIF_LEN, bar_t(1), 0.62)
    ep_line(ANSWER, ANSWER_BEATS, ANSWER_LEN, bar_t(2), 0.58)
    # brand (bars 3-4): comping + motif statement under the title (bar 4)
    for step, ln in [(0, 5), (6, 3), (11, 4)]:
        ep_chord(top4("Dmaj9"), bar_t(3) + step * S16, ln * S16, 0.42)
    for step, ln in [(0, 4), (6, 3), (11, 4)]:
        ep_chord(top4("A/C#"), bar_t(4) + step * S16, ln * S16, 0.38)
    ep_line(MOTIF, MOTIF_BEATS, MOTIF_LEN, bar_t(4), 0.55)
    # autosort (bars 5-6): comping that leaves the land cues alone
    for step, ln in [(0, 6), (10, 4)]:
        ep_chord(top4("F#m7"), bar_t(5) + step * S16, ln * S16, 0.36)
    for step, ln, ch in [(0, 2, "Esus4"), (5, 2, "Esus4"), (11, 4, "E")]:
        ep_chord(top4(ch), bar_t(6) + step * S16, ln * S16, 0.34)
    # tabs (bars 7-8): motif again over Dmaj9, answer over A/C# (avoiding 14.0 / 15.0)
    for step, ln in [(0, 6), (11, 4)]:
        ep_chord(top4("Dmaj9"), bar_t(7) + step * S16, ln * S16, 0.34)
    ep_line(MOTIF, MOTIF_BEATS, MOTIF_LEN, bar_t(7), 0.55)
    for step, ln in [(2, 4), (10, 2)]:
        ep_chord(top4("A/C#"), bar_t(8) + step * S16, ln * S16, 0.34)
    ep_line(["E5", "C#5", "A4"], [0.5, 1.5, 2.5], [0.6, 0.6, 0.9], bar_t(8), 0.5)
    # build (bars 9-10): sparse sustained chords under the typing
    ep_chord(top4("F#m7"), 16.0, 1.9, 0.40, rel=0.6)
    ep_chord(top4("Esus4"), 18.0, 0.95, 0.40)
    ep_chord(top4("E"), 19.0, 0.9, 0.46)
    # drop (bars 11-13): soft off-beat chords (piano-house lift under the stabs)
    for bar in (11, 12, 13):
        for step in (2, 6, 10, 14):
            t = bar_t(bar) + step * S16
            if t >= 25.7:
                continue
            ep_chord(top4(chord_at(t)), t, 1.2 * S16, 0.30, rel=0.15, roll=0.002)
    # end: the resolution chord
    ep_chord([midi("A2")] + voicing("Aadd9", "pad"), 26.0, 3.0, 0.62, rel=0.8, roll=0.006)

    # ---------------- soft pluck arp (dotted-8th delay on the bus) ----------------
    def arp(t, mn, vel, gate=0.3, t60=0.9, bright=0.45):
        B["arp"].add(ks_pluck(mn, gate, vel, rng, t60=t60, bright=bright, damp=0.55), t,
                     pan=0.28 if (round(t / S16) % 2) else -0.28)

    for bar in range(3, 9):                                    # brand, autosort, tabs
        for k in range(8):
            t = bar_t(bar) + k * 2 * S16
            if t >= 15.5 or near_land(t) or near_ui(t):
                continue
            tones = voicing(chord_at(t), "arp")
            v = (0.55 if bar < 5 else 0.6) * (1.0 if k % 2 == 0 else 0.8)
            arp(t, tones[ARP8[k]], v)
        if bar in (7, 8):                                      # 16th pickups in tabs
            for step in (7, 15):
                t = bar_t(bar) + step * S16
                if t < 15.5:
                    arp(t, voicing(chord_at(t), "arp")[3], 0.4)
    for i in range(int((GAP_START - 16.0) / S16) + 1):        # build: 16ths, filter opens
        t = 16.0 + i * S16
        if t >= GAP_START - 0.01:
            break
        if near_ui(t, 0.02):
            continue
        prog = max(0.0, (t - 17.9) / 2.04)
        arp(t, voicing(chord_at(t), "arp")[ARP16[i % 16]], 0.38 + 0.45 * prog, gate=0.12, t60=0.7)
    for bar in (11, 12, 13):                                   # drop: quiet 16th sparkle
        for i in range(16):
            t = bar_t(bar) + i * S16
            if t >= 25.7:
                continue
            arp(t, voicing(chord_at(t), "arp")[ARP16[i]] + 12, 0.22 * (1.0 if i % 2 == 0 else 0.7),
                gate=0.08, t60=0.5, bright=0.6)

    # ---------------- bass: sub (sustained, pumped) + mid (groove) ----------------
    def bass_part(bars, groove, stop, octave_step):
        for bar in bars:
            for step, ln in groove:
                t = bar_t(bar) + step * S16
                if t >= stop:
                    continue
                ch = chord_at(t)
                mn = bass_midi(ch) + (12 if step == octave_step else 0)
                if ch == "A/C#" and step == octave_step:
                    mn = midi("A2")                 # walk C# -> A: the slash chord keeps its root
                gate = min(ln * S16, stop - t) - 0.01
                B["bass"].add(bass_mid_note(mn, gate, 0.9 if step == 0 else 0.75,
                                            bright=0.45 if ch == "A/C#" else 1.0), t)
        for seg in SEGS:
            a, b = max(seg["t0"], bar_t(bars[0])), min(seg["t1"], stop)
            if b > a:
                B["sub"].add(sub_note(bass_midi(seg["chord"]) - 12, b - a - 0.02), a)

    bass_part(range(3, 9), BASS_GROOVE, 15.5, 14)
    bass_part(range(11, 14), DROP_RHYTHM, 25.75, 13)
    B["sub"].add(sub_note(midi("A1"), 1.5, rel=1.2, att=0.004), 26.0)
    B["bass"].add(bass_mid_note(midi("A2"), 1.6, 0.8, rel=1.0, bright=0.6), 26.0)

    # ---------------- stabs (drop) + final hit ----------------
    for bar in (11, 12, 13):
        for (step, ln), v in zip(DROP_RHYTHM, DROP_VEL):
            t = bar_t(bar) + step * S16
            B["stab"].add(stab_chord(voicing(chord_at(t), "stab"), ln * S16 - 0.02, v, rng), t)
    B["stab"].add(stab_chord(voicing("Aadd9", "stab"), 1.1, 0.75, rng, fc_lo=900, fc_hi=2600,
                             tau=0.4, rel=1.6, att=0.004), 26.0)

    # ---------------- lead hook (drop) ----------------
    for bar, beat, nm, ln, v in HOOK:
        B["lead"].add(lead_note(midi(nm), ln * BEAT, v, rng), bar_t(bar) + beat * BEAT)

    # ---------------- drums ----------------
    drng = np.random.default_rng(777)

    def hit(bus, x, t, gain=1.0, pan=0.0, human=0.0):
        B[bus].add(x, t + (drng.uniform(-human, human) if human else 0.0), gain, pan)

    for bar in range(3, 9):                         # brand / autosort / tabs
        sec = "brand" if bar < 5 else ("autosort" if bar < 7 else "tabs")
        for step in range(16):
            t = bar_t(bar) + step * S16
            if t >= 15.5 - 1e-9:
                continue
            if step % 4 == 0:
                hit("kick", kick(drng, 1.0), t)
                kicks.append(t)
            if step in (4, 12):
                hit("drums", clap(drng, 0.5 if near_land(t) else 1.0), t)
                B["drums"].onsets += [t + 0.0095, t + 0.0185, t + 0.0275]
                hit("drums", rim(drng, 0.35), t, pan=0.1)
            if step % 4 == 2 and not near_land(t) and not near_ui(t):
                hit("drums", hat(drng, 0.55 if sec == "brand" else 0.6), t, pan=0.25, human=0.002)
            if sec == "tabs" and step % 2 == 1 and not near_ui(t):
                hit("drums", hat(drng, 0.28), t, pan=0.3, human=0.002)
            if sec != "brand" and not near_ui(t) and not near_land(t, 0.02):
                hit("drums", shaker(drng, 0.3 if step % 2 else 0.42), t, pan=-0.3, human=0.003)
            if sec == "tabs" and step in (7, 14):
                hit("drums", rim(drng, 0.4), t, pan=-0.15)
    hit("drums", crash(drng, 0.55), 4.0, pan=0.0)

    for bar in (11, 12, 13):                        # drop
        for step in range(16):
            t = bar_t(bar) + step * S16
            if t >= 25.7:
                continue
            if step % 4 == 0:
                hit("kick", kick(drng, 1.0), t)
                kicks.append(t)
            if step in (4, 12):
                hit("drums", clap(drng, 1.0), t)
                B["drums"].onsets += [t + 0.0095, t + 0.0185, t + 0.0275]
                hit("drums", snare(drng, 0.55), t)
            if step in (3, 10):
                hit("drums", rim(drng, 0.38), t, pan=-0.2)
            if step % 4 == 2:
                hit("drums", hat(drng, 0.34, open_=True), t, pan=0.2, human=0.002)
            else:
                hit("drums", hat(drng, [0.5, 0.28, 0.0, 0.3][step % 4]), t, pan=0.25, human=0.002)
            hit("drums", shaker(drng, 0.32 if step % 2 else 0.45), t, pan=-0.3, human=0.003)
        if bar == 12:                               # little snare fill into bar 13
            for k, step in enumerate((13, 14, 15)):
                hit("drums", snare(drng, 0.35 + 0.15 * k, tune=1.0 + 0.05 * k), bar_t(12) + step * S16)
    hit("drums", crash(drng, 1.0), 20.0)
    hit("drums", crash(drng, 0.6), 24.0)
    return B, kicks


def process_music(B, kicks):
    """Tone, dynamics, sends and reverb returns for the music; returns stereo music + parts."""
    # ---- sidechain curves ----
    sc = lambda depth, rel=0.2: duck_curve(kicks, depth, attack=0.003, hold=0.01, release=rel)
    pump_times = ([16.0 + i * BEAT for i in range(4)] + [18.0 + i * 2 * S16 for i in range(4)] +
                  [19.0 + i * S16 for i in range(7)])
    build_pump = duck_curve(pump_times, 0.28, attack=0.003, hold=0.005, release=0.1)

    # pad: rising intro filter, breakdown dip, re-open for the drop
    pad_fc = curve([(0, 260), (1.0, 360), (3.95, 1900), (4.0, 2600), (15.4, 2600), (15.95, 1000),
                    (16.0, 950), (19.9, 3400), (20.0, 3600), (25.95, 3600), (26.0, 3000),
                    (29.8, 900)], log=True)
    B["pad"].map(lambda x: svf(x, pad_fc, 0.6, "lp")).map(lambda x: chorus(x, 0.35, 0.3, 11, 0.4))
    B["pad"].gain(sc(0.45) * build_pump)

    # e-piano: stereo tremolo (autopan) + light chorus
    trem = 0.12 * np.sin(2 * np.pi * 4.2 * _t(N))
    B["ep"].map(lambda x: np.stack([x[0] * (1 + trem), x[1] * (1 - trem)]))
    B["ep"].map(lambda x: chorus(x, 0.8, 0.15, 7, 0.25))
    B["ep"].gain(sc(0.2))

    # arp: filter opens through the build, dotted-8th delay
    arp_fc = curve([(0, 5200), (15.95, 5200), (16.0, 480), (17.95, 800), (19.9, 6500), (20.0, 7000),
                    (30, 7000)], log=True)
    B["arp"].map(lambda x: svf(x, arp_fc, 0.8, "lp"))
    B["arp"].map(lambda x: x + 0.38 * tap_delay(x, 3 * S16, 0.42, 5,       # dotted 8th = 0.375 s
                                                   spread=0.55, lp=4200, hp=350))
    B["arp"].gain(sc(0.25))

    B["sub"].gain(sc(0.88, 0.18))
    B["bass"].gain(sc(0.5, 0.16))
    B["stab"].map(lambda x: chorus(x, 0.6, 0.2, 8, 0.25)).gain(sc(0.62, 0.21))
    B["lead"].map(lambda x: x + 0.42 * tap_delay(x, 3 * S16, 0.4, 6, spread=0.9, lp=5500, hp=450))
    B["lead"].gain(sc(0.15))

    board = pb.Pedalboard([pb.Compressor(threshold_db=-18, ratio=2.5, attack_ms=3, release_ms=90)])
    B["drums"].map(lambda x: board(x.astype(np.float32), SR).astype(np.float64))

    # ---- per-section faders (dB), applied before the sends so the reverbs follow ----
    for name, table in MIX_DB.items():
        B[name].gain(section_gain(table))

    # ---- sends / reverb returns ----
    hall = Bus("hall")
    plate = Bus("plate")
    room = Bus("room")
    for name, lv in [("pad", 0.32), ("ep", 0.24), ("arp", 0.22), ("stab", 0.2), ("lead", 0.2)]:
        B[name].send_to(hall, lv)
    for name, lv in [("ep", 0.14), ("arp", 0.18), ("lead", 0.16), ("drums", 0.08)]:
        B[name].send_to(plate, lv)
    B["drums"].send_to(room, 0.18)
    hall.map(lambda x: convolve_st(filt(x, "highpass", 180, 2), IR_HALL))
    plate.map(lambda x: convolve_st(filt(x, "highpass", 250, 2), IR_PLATE))
    room.map(lambda x: convolve_st(filt(x, "highpass", 300, 2), IR_ROOM))
    hall.gain(duck_curve(kicks, 0.3, release=0.25))

    parts = {k: v.mix() for k, v in B.items()}
    parts["hall"] = hall.mix() * section_gain(RETURN_DB["hall"])
    parts["plate"] = plate.mix() * section_gain(RETURN_DB["plate"])
    parts["room"] = room.mix() * section_gain(RETURN_DB["room"])
    onsets = set(t for b in B.values() for t in b.onsets)
    for name in ("arp", "lead"):                       # dotted-8th echoes re-articulate notes
        onsets |= set(t + 3 * S16 * k for t in B[name].onsets for k in range(1, 7))
    return parts, sorted(onsets)


# =============================================================================
# 6. SFX
# =============================================================================

def pop_sound(rng, mn, vel, decay=0.04, glide=0.25, bright=1.0):
    """Soft glassy pop: sine with a quick upward glide, 2nd/3rd partial, tiny tick."""
    n = int(0.25 * SR)
    t = _t(n)
    f = hz(mn)
    fi = f * (1.0 - glide * np.exp(-t / 0.007))
    ph = 2 * np.pi * np.concatenate(([0.0], np.cumsum(fi[:-1]))) / SR
    tone = (np.sin(ph) + bright * 0.22 * np.sin(2 * ph + 0.3) * np.exp(-t / (decay * 0.4))
            + 0.06 * np.sin(3 * ph) * np.exp(-t / (decay * 0.25)))
    env = (1 - np.exp(-t / 0.00035)) * np.exp(-t / decay)
    tick = filt(rng.standard_normal(n), "highpass", 2500) * np.exp(-t / 0.0006) * 0.22 * bright
    return tail_fade((tone * env + tick) * vel, 0.01)


def bell(rng, mn, vel, dur=3.0, bright=1.0):
    """Struck glass/bell: inharmonic partials + a short FM glint."""
    f = hz(mn)
    n = int(dur * SR)
    t = _t(n)
    ks = 2.0 ** (-(mn - 81) / 24.0)
    parts = [(1.0, 1.0, 2.4), (2.0, 0.28, 1.4), (2.76, 0.30, 0.9), (4.07, 0.12, 0.55),
             (5.40, 0.10, 0.35), (8.93, 0.04, 0.18)]
    x = np.zeros(n)
    for r, a, tau in parts:
        if f * r < 0.45 * SR:
            x += a * np.sin(2 * np.pi * f * r * t + rng.uniform(0, 0.3)) * np.exp(-t / (tau * ks))
    x += 0.15 * bright * np.sin(2 * np.pi * f * t + 1.2 * np.exp(-t / 0.02) *
                                np.sin(2 * np.pi * 3.5 * f * t)) * np.exp(-t / 0.1)
    x *= 1 - np.exp(-t / 0.0004)
    return tail_fade(x * vel, 0.3)


def whoosh(rng, dur, f_lo=400, f_hi=3200, peak=0.6, pan0=-0.5, pan1=0.5, q=1.1, air=0.3):
    n = int(dur * SR)
    t = _t(n)
    x = t / dur
    env = np.where(x < peak, np.sin(0.5 * np.pi * x / peak) ** 2,
                   np.cos(0.5 * np.pi * (x - peak) / (1 - peak)) ** 2)
    fc = f_lo * (f_hi / f_lo) ** env
    nz = filt(rng.standard_normal(n), "lowpass", 9000, 1)
    y = svf(nz, fc, q, "bp") + air * filt(rng.standard_normal(n), "highpass", 5000) * env
    y *= env
    p = pan0 + (pan1 - pan0) * x
    gl, gr = pan_gains(p)
    return np.stack([y * gl, y * gr])


def riser(rng, dur, f0=350, f1=7000, power=2.2, tone=None, tone_gain=0.25):
    n = int(dur * SR)
    t = _t(n)
    x = t / dur
    fc = f0 * (f1 / f0) ** (x ** 1.3)
    amp = x ** power
    y = svf(st_noise(rng, n, 0.7), fc, 1.6, "bp") * amp
    if tone is not None:
        m0, m1 = tone
        f = hz(m0) * (hz(m1) / hz(m0)) ** x * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * t))
        y += tone_gain * sine(f, n, SR) * amp
    k = int(0.004 * SR)
    y[:, -k:] *= np.linspace(1, 0, k)
    return y


def impact(rng, size=1.0):
    """Sub drop + transient + short noise crack; returns (dry, splash-send source)."""
    n = int(3.5 * SR)
    t = _t(n)
    f_sub = 30.0 + (70.0 + 25.0 * (size - 1)) * np.exp(-t / (0.22 * size))
    sub = sine(f_sub, n) * np.exp(-t / (0.55 * size)) * (1 - np.exp(-t / 0.001))
    sub = np.tanh(1.5 * sub) / np.tanh(1.5)
    f_b = 48.0 + 120.0 * np.exp(-t / 0.03)
    body = sine(f_b, n) * np.exp(-t / 0.12) * (1 - np.exp(-t / 0.0005))
    tr = (filt(rng.standard_normal(n), "highpass", 1200) * np.exp(-t / 0.0025)
          + 0.5 * np.sin(2 * np.pi * 2800 * t) * np.exp(-t / 0.0012))
    crack = filt(st_noise(rng, n, 0.6), "lowpass", 6000) * np.exp(-t / (0.06 * size))
    dry = to_stereo(0.9 * sub + 0.6 * body + 0.35 * tr) + 0.25 * crack
    splash = to_stereo(0.5 * tr + 0.2 * body) + 0.6 * crack
    return tail_fade(dry, 0.3), splash


def impact_soft(rng):
    n = int(3.0 * SR)
    t = _t(n)
    f_sub = hz(midi("A1")) + 15.0 * np.exp(-t / 0.06)
    sub = sine(f_sub, n) * np.exp(-t / 0.9) * (1 - np.exp(-t / 0.002))
    thump = sine(60.0 + 50.0 * np.exp(-t / 0.02), n) * np.exp(-t / 0.08) * (1 - np.exp(-t / 0.0005))
    tr = (filt(rng.standard_normal(n), "lowpass", 3500) * np.exp(-t / 0.003)
          + 0.5 * filt(rng.standard_normal(n), "highpass", 3000) * np.exp(-t / 0.0004))
    dry = to_stereo(0.6 * sub + 0.45 * thump + 0.35 * tr)
    return tail_fade(dry, 0.3), to_stereo(0.4 * tr + 0.2 * thump)


def land_sound(rng, mn):
    n = int(0.9 * SR)
    t = _t(n)
    pl = np.zeros(n)
    k = ks_pluck(mn, 0.45, 1.0, rng, t60=1.2, bright=0.8, damp=0.35, rel=0.25, sine_mix=0.3)
    pl[:k.size] = k[:n]
    f = hz(mn)
    glass = (np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.05)
             + 0.3 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t / 0.03)) * (1 - np.exp(-t / 0.0004))
    pop = np.zeros(n)
    p = pop_sound(rng, mn + 12, 1.0, decay=0.03, glide=0.2)
    pop[:p.size] = p
    thud = sine(110.0 + 70.0 * np.exp(-t / 0.01), n) * np.exp(-t / 0.03) * (1 - np.exp(-t / 0.0006))
    tick = filt(rng.standard_normal(n), "highpass", 3000) * np.exp(-t / 0.0006)
    return tail_fade(0.55 * pl + 0.18 * glass + 0.3 * pop + 0.22 * thud + 0.12 * tick, 0.05)


def snap_sound(rng):
    """Magnetic dock: two quick transients 28 ms apart."""
    n = int(0.3 * SR)
    t = _t(n)

    def click(o, fr, tau, fb, lvl):
        tt = np.maximum(t - o, 0.0)
        on = (t >= o).astype(float)
        x = (filt(rng.standard_normal(n), "highpass", 2500) * np.exp(-tt / 0.0015)
             + 0.7 * np.sin(2 * np.pi * fr * tt) * np.exp(-tt / tau)
             + 0.6 * np.sin(2 * np.pi * (fb + 60 * np.exp(-tt / 0.01)) * tt) * np.exp(-tt / 0.035))
        return x * on * (1 - np.exp(-tt / 0.0002)) * lvl

    x = click(0.0, 2900, 0.012, 170, 1.0) + click(0.028, 4200, 0.008, 240, 0.8)
    return tail_fade(x, 0.02)


def ui_click(rng, pitch=1.0):
    n = int(0.08 * SR)
    t = _t(n)
    x = (0.6 * np.sin(2 * np.pi * 1900 * pitch * t) * np.exp(-t / 0.0025)
         + 0.35 * np.sin(2 * np.pi * 820 * pitch * t) * np.exp(-t / 0.009)
         + 0.25 * filt(rng.standard_normal(n), "highpass", 3500) * np.exp(-t / 0.0006))
    return tail_fade(x * (1 - np.exp(-t / 0.00015)), 0.01)


def key_sound(rng, kind="key"):
    """Laptop (scissor) key: contact click, keycap bottom-out tick, small thock, chassis ring."""
    n = int(0.08 * SR)
    t = _t(n)
    fc = rng.uniform(2600, 5200)
    contact = filt(rng.standard_normal(n), "bandpass", [fc * 0.7, min(fc * 1.45, 16000)]) \
        * np.exp(-t / rng.uniform(0.0008, 0.0016))
    d2 = rng.uniform(0.0025, 0.005)
    tt = np.maximum(t - d2, 0)
    bottom = (t >= d2) * filt(rng.standard_normal(n), "bandpass", [1200, 4200]) * np.exp(-tt / 0.0012)
    fb = rng.uniform(260, 420)
    tb = rng.uniform(0.006, 0.010)
    lvl = rng.uniform(0.75, 1.0)
    if kind == "space":
        fb, tb = rng.uniform(150, 190), 0.018
    if kind == "enter":
        fb, tb, lvl = 175.0, 0.02, 1.35
    thock = np.sin(2 * np.pi * fb * t) * np.exp(-t / tb)
    ring = np.sin(2 * np.pi * rng.uniform(1300, 2000) * t) * np.exp(-t / 0.004)
    x = 0.9 * contact + rng.uniform(0.4, 0.8) * bottom + 0.45 * thock + 0.12 * ring
    if kind in ("space", "enter"):
        x += 0.3 * (t >= 0.006) * filt(rng.standard_normal(n), "bandpass", [700, 2500]) \
            * np.exp(-np.maximum(t - 0.006, 0) / 0.006)
    return tail_fade(x * (1 - np.exp(-t / 0.0001)) * lvl, 0.01)


def tick_sound(rng, f):
    n = int(0.06 * SR)
    t = _t(n)
    x = (0.7 * np.sin(2 * np.pi * f * t) * np.exp(-t / 0.006)
         + 0.3 * np.sin(2 * np.pi * f * 1.5 * t) * np.exp(-t / 0.003)
         + 0.4 * filt(rng.standard_normal(n), "highpass", 4000) * np.exp(-t / 0.0005)
         + 0.3 * np.sin(2 * np.pi * 900 * t) * np.exp(-t / 0.008))
    return tail_fade(x * (1 - np.exp(-t / 0.0001)), 0.01)


def shimmer(rng, dur, pcs, n_bells=26, sweep=(-0.7, 0.7)):
    n = int((dur + 2.5) * SR)
    out = np.zeros((2, n))
    times = np.sort(rng.beta(2.0, 2.2, n_bells) * dur)
    last = None
    for tb in times:
        choices = [p for p in pcs if p != last] or pcs
        pc = choices[rng.integers(len(choices))]
        last = pc
        mn = midi(pc + ("6" if rng.random() < 0.6 else "7"))
        mn = min(mn, midi("B7") - 12)
        b = bell(rng, mn, rng.uniform(0.3, 1.0), dur=1.2, bright=0.6)
        p = sweep[0] + (sweep[1] - sweep[0]) * tb / dur + rng.uniform(-0.2, 0.2)
        i0 = int(tb * SR)
        out[:, i0:i0 + b.size] += to_stereo(b, p)[:, :n - i0]
    t = _t(n)
    x = np.clip(t / dur, 0, 1)
    air_env = np.sin(np.pi * x) ** 2 * (t < dur)
    air = filt(st_noise(rng, n, 0.6), "highpass", 7000, 2) * air_env * 0.25
    return out * 0.35 + air


def downlifter(rng, dur):
    n = int(dur * SR)
    t = _t(n)
    x = t / dur
    fc = 5000.0 * (250.0 / 5000.0) ** x
    env = (1 - x) ** 1.5 * np.minimum(t / 0.02, 1.0)
    y = svf(st_noise(rng, n, 0.7), fc, 1.3, "bp") * env
    y += 0.15 * sine(hz(81) * (hz(57) / hz(81)) ** x, n) * env
    return tail_fade(y, 0.01)


def snare_roll_times(t0, t1, p0=0.125, p1=0.0208):
    ts = []
    t = t0
    while t < t1 - 0.012:
        ts.append(t)
        prog = (t - t0) / (t1 - t0)
        t += p0 * (p1 / p0) ** prog
    return ts


def reverse_swell(rng, chord, dur):
    """Reversed hall tail of the next chord (Dmaj9), so it swells into the downbeat."""
    notes = voicing(chord, "arp")
    m = int(3.2 * SR)
    hit = np.zeros((2, m))
    for mn in notes:
        e = to_stereo(ep_note(mn, 0.2, 0.9, rel=0.3))
        hit[:, :e.shape[1]] += e[:, :m]
        b = bell(rng, mn + 12, 0.4, dur=1.5)
        hit[:, :b.size] += to_stereo(b)[:, :m]
    wet = np.stack([signal.oaconvolve(hit[c], IR_HALL[c])[:m] for c in range(2)])
    rev = wet[:, ::-1]
    k = int(dur * SR)
    y = rev[:, -k:].copy()
    y *= np.sin(0.5 * np.pi * np.clip(_t(k) / (dur * 0.7), 0, 1)) ** 2
    y /= np.max(np.abs(y)) + 1e-12
    j = int(0.003 * SR)
    y[:, -j:] *= np.linspace(1, 0, j)
    return y


def compose_sfx():
    rng = np.random.default_rng(4242)
    S = {k: Bus(k) for k in ["ui", "glass", "sweep", "big", "drum"]}
    splash = Bus("splash")

    def place(bus, x, t, gain, pan=0.0, align_end=None):
        t0 = t if align_end is None else align_end - np.asarray(x).shape[-1] / SR
        S[bus].add(x, t0, gain, pan)

    # intro pops (very soft, pitched to the chord, never the same pitch twice in a row)
    pops = [c for c in SFX if c["type"] == "pop" and c.get("gain") == "very soft"]
    last = None
    for i, c in enumerate(pops):
        t = c["t"]
        tones = chord_tone_names(chord_at(t))
        choices = [p for p in tones if p != last]
        pc = choices[rng.integers(len(choices))]
        last = pc
        octv = 5 if rng.random() < 0.55 else 6
        mn = midi(pc + str(octv))
        gap = min([abs(t - o["t"]) for o in pops if o is not c] + [0.3])
        dens = float(np.clip(gap / 0.2, 0.45, 1.0)) ** 0.6
        vel = 0.15 * rng.uniform(0.6, 1.0) * dens
        dec = rng.uniform(0.028, 0.05) * (0.75 if gap < 0.08 else 1.0)
        place("glass", pop_sound(rng, mn, vel, decay=dec, glide=rng.uniform(0.12, 0.35),
                                 bright=rng.uniform(0.5, 1.0)), t, 1.0, pan=rng.uniform(-0.6, 0.6))

    for c in SFX:
        typ, t = c["type"], float(c["t"])
        until = float(c.get("until", t))
        if typ == "riser":
            if t < 10:
                place("sweep", riser(rng, until - t, 350, 6500, 2.4, tone=(57, 81), tone_gain=0.18),
                      t, 0.18)
            else:
                d = GAP_START - t
                place("sweep", riser(rng, d, 400, 9000, 2.0, tone=(64, 88), tone_gain=0.22), t, 0.22)
        elif typ == "reverse-swell":
            place("sweep", reverse_swell(rng, chord_at(until + 0.01), until - t), t, 0.28)
        elif typ == "impact":
            size = 1.0 if t < 10 else 1.5
            dry, spl = impact(rng, size)
            place("big", dry, t, 0.66 if size == 1.0 else 0.7)
            splash.add(spl, t, 0.5 if size == 1.0 else 0.75)
        elif typ == "impact-soft":
            dry, spl = impact_soft(rng)
            place("big", dry, t, 0.62)
            splash.add(spl, t, 0.4)
        elif typ == "whoosh":
            d = until - t
            if abs(t - 4.0) < 1e-6:        # icons fly in: a flurry of small whooshes
                for k in range(5):
                    o = 0.06 * k
                    place("sweep", whoosh(rng, d - o * 0.8, 500, 3500, 0.35, pan0=rng.uniform(-0.8, 0),
                                          pan1=rng.uniform(0, 0.8)), t + o, 0.07)
            else:
                pk = 0.8 if until in (26.0, 12.05, 8.05) else 0.6
                place("sweep", whoosh(rng, d, 350, 3000, pk, pan0=-0.6 if t < 10 else 0.6,
                                      pan1=0.6 if t < 10 else -0.6), t, 0.22)
        elif typ == "whoosh-short":
            place("sweep", whoosh(rng, until - t, 700, 4200, 0.85, pan0=0.3, pan1=-0.1, air=0.4), t, 0.17)
        elif typ == "shimmer":
            pcs = chord_tone_names(chord_at(t + 0.01))
            place("glass", shimmer(rng, until - t, pcs), t, 0.28 if t < 10 else 0.45)
        elif typ == "land":
            k = LAND_TIMES.index(t)
            mn = midi(["C#5", "E5", "A5", "B5"][k])
            place("glass", land_sound(rng, mn), t, 0.66, pan=[-0.35, 0.35, -0.2, 0.2][k])
        elif typ == "snap":
            place("ui", snap_sound(rng), t, 0.48, pan=0.1)
        elif typ == "click":
            place("ui", ui_click(rng, 1.0 if t < 14.5 else 1.12), t, 0.95, pan=0.15)
        elif typ == "downlifter":
            place("sweep", downlifter(rng, until - t), t, 0.2)
        elif typ == "ui-open":
            place("sweep", whoosh(rng, 0.19, 900, 3600, 0.4, pan0=-0.25, pan1=0.2, air=0.2), t, 0.18)
            for k, nm in enumerate(["C#6", "F#6"]):
                b = bell(rng, midi(nm), 0.5, 0.35)
                b *= np.exp(-_t(b.size) / 0.07)
                place("glass", b, t + 0.02 + 0.07 * k, 0.14)
        elif typ == "key":
            idx = sum(1 for o in SFX if o["type"] == "key" and o["t"] < t)
            kind = "space" if idx in (3, 6, 9, 13, 17, 22) else "key"
            place("ui", key_sound(rng, kind), t, 0.34, pan=rng.uniform(-0.15, 0.15))
        elif typ == "enter":
            place("ui", key_sound(rng, "enter"), t, 0.3, pan=0.1)
        elif typ == "tick":
            f = {18.0: hz(95), 18.5: hz(97), 19.0: hz(100), 19.4: hz(102)}.get(round(t, 2), hz(100))
            place("ui", tick_sound(rng, f), t, {18.0: 0.2, 18.5: 0.4, 19.0: 0.4}.get(round(t, 2), 0.4),
                  pan=0.2)
        elif typ == "pop":
            if c.get("gain") == "medium":
                x = pop_sound(rng, midi("E5"), 1.0, decay=0.08, glide=0.3) + \
                    0.5 * pop_sound(rng, midi("B5"), 1.0, decay=0.05, glide=0.2)
                place("glass", x, t, 0.14, pan=-0.1)
        elif typ == "swoosh":
            k = [o["t"] for o in SFX if o["type"] == "swoosh"].index(t)
            place("sweep", whoosh(rng, 0.17, 600 + 150 * k, 3600 + 400 * k, 0.4, pan0=-0.6,
                                  pan1=0.6, air=0.35), t, 0.075)
        elif typ == "snare-roll":
            ticks = [o["t"] for o in SFX if o["type"] == "tick"]
            ts = [x for x in snare_roll_times(t, until)
                  if all(abs(x - tk) > 0.02 or abs(x - tk) < 1e-9 for tk in ticks)]
            for k, tr in enumerate(ts):
                prog = (tr - t) / (until - t)
                ghost = any(0.0 < tk - tr <= 0.045 for tk in ticks)
                x = snare(rng, 0.3 + 0.7 * prog ** 1.5, tune=1.0 + 0.35 * prog, decay=0.09, body=0.8)
                S["drum"].add(x, tr, 0.36 * (0.4 if ghost else 1.0), pan=0.15 if k % 2 else -0.15)
        elif typ == "chime":
            for k, nm in enumerate(["A5", "C#6", "E6", "B6"]):
                S["glass"].add(bell(rng, midi(nm), [1.0, 0.8, 0.75, 0.7][k], dur=3.5), t + 0.075 * k,
                               0.17, pan=[-0.3, -0.1, 0.1, 0.3][k])

    # buses -> reverbs
    plate = Bus("sfxplate")
    hall = Bus("sfxhall")
    S["glass"].send_to(hall, 0.35)
    S["glass"].send_to(plate, 0.2)
    S["ui"].send_to(plate, 0.1)
    S["sweep"].send_to(hall, 0.25)
    S["drum"].send_to(plate, 0.2)
    hall.map(lambda x: convolve_st(filt(x, "highpass", 200), IR_HALL))
    plate.map(lambda x: convolve_st(filt(x, "highpass", 300), IR_PLATE))
    splash.map(lambda x: convolve_st(filt(x, "highpass", 250), IR_SPLASH))
    parts = {k: v.mix() for k, v in S.items()}
    parts["sfxhall"] = hall.mix() * 0.6
    parts["sfxplate"] = plate.mix() * 0.5
    parts["splash"] = splash.mix() * 0.55
    return parts


# =============================================================================
# 7. MIX + MASTER
# =============================================================================

DUCK = {"impact": (2.5, 0.30), "impact-soft": (2.0, 0.40), "land": (4.0, 0.22), "snap": (4.0, 0.25),
        "click": (4.0, 0.18), "chime": (3.0, 0.60), "tick": (2.5, 0.12), "enter": (3.0, 0.15)}


def cue_duck():
    g = np.ones(N)
    for typ, (dbv, rel) in DUCK.items():
        ts = [c["t"] for c in SFX if c["type"] == typ]
        g *= duck_curve(ts, 1 - db(-dbv), attack=0.008, hold=0.03, release=rel)
    ts = [c["t"] for c in SFX if c["type"] == "pop" and c.get("gain") == "medium"]
    g *= duck_curve(ts, 1 - db(-2.5), attack=0.008, hold=0.03, release=0.2)
    typing = curve([(0, 1), (16.35, 1), (16.45, db(-2.5)), (17.95, db(-2.5)), (18.1, 1), (30, 1)])
    return g * typing


GAP_GATE = np.ones(N)
GAP_GATE[int(round(GAP_START * SR)):int(round(DROP * SR))] = 0.0


def end_fade():
    t = _t(N)
    x = np.clip((t - FADE_START) / (FADE_END - FADE_START), 0, 1)
    g = np.cos(0.5 * np.pi * x) ** 2
    g[t >= FADE_END] = 0.0
    return g


def lf_mono(x, fc=150.0):
    """Keep everything below ~150 Hz mono: high-pass the side channel (zero phase)."""
    sos_ = signal.butter(4, fc, "highpass", fs=SR, output="sos")
    m = 0.5 * (x[0] + x[1])
    s = signal.sosfilt(sos_, 0.5 * (x[0] - x[1]))       # causal: nothing leaks into the gap
    return np.stack([m + s, m - s])


def dc_block(x):
    return signal.sosfilt(signal.butter(2, 18.0, "highpass", fs=SR, output="sos"), x, axis=-1)


def oversampled_abs(x, os_=4):
    up = signal.resample_poly(x, os_, 1, axis=-1)
    a = np.abs(up).max(axis=0)
    return a.reshape(-1, os_).max(axis=1)[: x.shape[1]]


def true_peak_db(x, os_=4):
    return 20 * np.log10(np.max(oversampled_abs(x, os_)) + 1e-12)


@njit(cache=False)
def _lim_gain(req, L, rel_coef):
    n = req.shape[0]
    gmin = np.empty(n)
    for i in range(n):
        m = 1.0
        j0 = i - L + 1
        if j0 < 0:
            j0 = 0
        for j in range(j0, i + 1):
            if req[j] < m:
                m = req[j]
        gmin[i] = m
    g = np.empty(n)
    prev = 1.0
    for i in range(n):
        rec = 1.0 - (1.0 - prev) * rel_coef
        v = gmin[i] if gmin[i] < rec else rec
        g[i] = v
        prev = v
    out = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += g[i]
        if i >= L:
            acc -= g[i - L]
        out[i] = acc / min(i + 1, L)
    return out


def tp_limiter(x, ceiling_db=-1.3, look=0.0015, release=0.08):
    """Look-ahead limiter driven by a 4x oversampled (true-peak) detector."""
    peak = oversampled_abs(x, 4)
    peak = np.maximum(peak, np.concatenate(([0.0], peak[:-1])))
    req = np.minimum(1.0, db(ceiling_db) / np.maximum(peak, 1e-12))
    L = int(look * SR)
    g = _lim_gain(np.ascontiguousarray(req), L, math.exp(-1.0 / (release * SR)))
    g = np.concatenate([g[L - 1:], np.ones(L - 1)])
    return x * g, g


def glue(music, sfx, target=-14.0):
    """Gentle bus compression of the music, with its threshold defined at the final master
    level (estimated from a first loudness pass)."""
    meter = pyln.Meter(SR)
    g0 = target - meter.integrated_loudness((music + sfx).T)
    board = pb.Pedalboard([pb.Compressor(threshold_db=-12.0, ratio=2.0, attack_ms=12.0, release_ms=140.0)])
    y = board((music * db(g0)).astype(np.float32), SR).astype(np.float64)
    return y / db(g0)


def master(music, sfx, target=-14.0):
    meter = pyln.Meter(SR)
    pre = lf_mono(dc_block(music + sfx))
    fade = end_fade() * GAP_GATE
    pre *= fade
    gdb = 0.0
    ceiling = -1.3
    for _ in range(12):
        y, g = tp_limiter(pre * db(gdb), ceiling)
        L = meter.integrated_loudness(y.T)
        tp = true_peak_db(y)
        if abs(L - target) < 0.02 and tp <= -1.05:
            break
        if tp > -1.05:
            ceiling -= 0.1
        gdb += target - L
    y[:, int(FADE_END * SR):] = 0.0
    stems = dict(music=lf_mono(dc_block(music)) * fade * db(gdb), sfx=lf_mono(dc_block(sfx)) * fade * db(gdb))
    for s in stems.values():
        s[:, int(FADE_END * SR):] = 0.0
    return y, g, gdb, ceiling, stems


# =============================================================================
# 8. ANALYSIS + REPORT
# =============================================================================

def k_weight(x):
    b1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    a1 = [1.0, -1.69065929318241, 0.73248077421585]
    b2 = [1.0, -2.0, 1.0]
    a2 = [1.0, -1.99004745483398, 0.99007225036621]
    return signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=-1), axis=-1)


def short_term(x, win=3.0, hop=0.1):
    p = (k_weight(x) ** 2).sum(axis=0)
    c = np.concatenate([[0.0], np.cumsum(p)])
    w = int(win * SR)
    st = np.arange(0, N - w + 1, int(hop * SR))
    ms = (c[st + w] - c[st]) / w
    return st / SR, -0.691 + 10 * np.log10(ms + 1e-12)


def section_loudness(x):
    ts, L = short_term(x)
    out = {}
    for name, a, b in SECTIONS:
        m = (ts >= a - 1e-9) & (ts + 3.0 <= b + 1e-9)
        vals = L[m]
        pw = 10 ** (vals / 10)
        seg = x[:, int(a * SR):int(b * SR)]
        ung = -0.691 + 10 * np.log10(((k_weight(seg) ** 2).sum(axis=0)).mean() + 1e-12)
        out[name] = dict(short_term_mean_lufs=round(float(10 * np.log10(pw.mean())), 2),
                         short_term_max_lufs=round(float(vals.max()), 2),
                         ungated_section_lufs=round(float(ung), 2))
    return out, ts, L


def detect_onsets(x, thr_db=9.0, floor_db=-72.0, refractory=0.012):
    """Energy-ratio onset detector on the (250 Hz high-passed) signal. 1 ms trailing
    'fast' window vs the preceding 10 ms 'slow' window; onset = first sample where the
    ratio exceeds thr_db. Trailing windows never report an onset before it happens."""
    y = filt(x, "highpass", 250, 2)
    p = (y ** 2).sum(axis=0)
    c = np.concatenate([[0.0], np.cumsum(p)])
    wf, ws = 48, 480
    i = np.arange(1, N + 1)
    a = np.maximum(i - wf, 0)
    b = np.maximum(i - wf - ws, 0)
    fast = (c[i] - c[a]) / wf
    slow = (c[a] - c[b]) / ws
    fl = 10 ** (floor_db / 10)
    ratio = 10 * np.log10((fast + fl) / (slow + fl))
    cond = (ratio > thr_db) & (fast > fl * 10)
    edges = np.flatnonzero(cond[1:] & ~cond[:-1]) + 1
    out = []
    lastt = -1.0
    for e in edges:
        t = e / SR
        if t - lastt >= refractory:
            out.append(t)
            lastt = t
    return np.array(out)


ONSET_TYPES = ["impact", "pop", "land", "click", "snap", "tick", "enter", "chime", "impact-soft"]


def cue_salience(music, sfx):
    """SFX-to-music K-weighted energy ratio per cue: first 80 ms for hits, the whole span for
    sweeps (whoosh/riser/...); a coarse 'does the cue read' number."""
    mk, sk = k_weight(music), k_weight(sfx)
    out = {}
    for c in SFX:
        t = float(c["t"])
        t1 = float(c["until"]) if "until" in c else t + 0.08
        i0, i1 = int(t * SR), int(t1 * SR)
        em = (mk[:, i0:i1] ** 2).sum()
        es = (sk[:, i0:i1] ** 2).sum()
        out.setdefault(c["type"], []).append(round(float(10 * np.log10((es + 1e-20) / (em + 1e-20))), 1))
    return out


def onset_report(sfx):
    det = detect_onsets(sfx)
    rows = []
    for c in SFX:
        if c["type"] not in ONSET_TYPES + ["key"]:
            continue
        t = float(c["t"])
        cand = det[(det >= t - 0.015) & (det <= t + 0.025)]
        if cand.size:
            o = float(cand[np.argmin(np.abs(cand - t))])
            rows.append(dict(t=t, type=c["type"], required=c["type"] != "key",
                             onset=round(o, 5), error_ms=round((o - t) * 1000, 2)))
        else:
            rows.append(dict(t=t, type=c["type"], required=c["type"] != "key", onset=None, error_ms=None))
    # transient peak for impacts (perceptual attack at the cue)
    mono = np.abs(sfx).max(axis=0)
    for r in rows:
        if r["type"] in ("impact", "impact-soft", "snap", "land", "chime"):
            i0 = int(r["t"] * SR)
            seg = mono[i0:i0 + int(0.03 * SR)]
            r["peak_after_ms"] = round(float(np.argmax(seg)) / SR * 1000, 2)
    return rows, det


def template(root_pc, intervals, root_w=1.5):
    v = np.zeros(12)
    for iv in intervals:
        v[(root_pc + iv) % 12] = 1.0
    v[root_pc % 12] = root_w
    return v


def harmonic_spectrogram(x_mono, nfft=16384, hop=2048):
    """Median-filter harmonic/percussive separation (Fitzgerald 2010): keep the harmonic
    part so hats/claps/kick sweeps do not smear the chroma."""
    from scipy.ndimage import median_filter
    f, tt, Z = signal.stft(x_mono, SR, window="hann", nperseg=nfft, noverlap=nfft - hop,
                           boundary=None, padded=False)
    S = np.abs(Z)
    H = median_filter(S, size=(1, 9))
    P = median_filter(S, size=(17, 1))
    mask = H ** 2 / (H ** 2 + P ** 2 + 1e-20)
    return f, tt + nfft / 2 / SR, (S * mask) ** 2


_HSPEC = {}


def chroma_of(x_mono, t0, t1):
    key = id(x_mono)
    if key not in _HSPEC:
        _HSPEC.clear()
        _HSPEC[key] = harmonic_spectrogram(x_mono)
    f, tt, PS = _HSPEC[key]
    m = (tt >= t0) & (tt <= t1)
    P = PS[:, m].mean(axis=1)
    chroma = np.zeros(12)
    for m in range(36, 101):          # C2 .. E7, one band per semitone
        lo, hi = hz(m - 0.5), hz(m + 0.5)
        e = P[(f >= lo) & (f < hi)].sum()
        chroma[m % 12] += math.sqrt(e)
    return chroma / (chroma.max() + 1e-12)


def chord_label(root_pc, q):
    return PC_NAMES[root_pc] + {"maj": "", "min": "m", "m7": "m7", "m9": "m9", "maj9": "maj9",
                                "sus4": "sus4", "add9": "add9"}[q]


def chord_report(music):
    mono = music.mean(axis=0)
    rows = []
    for s in SEGS:
        t0, t1 = s["t0"] + 0.18, min(s["t1"], 29.6) - 0.18   # whole STFT frame inside the segment
        ch = chroma_of(mono, t0, t1)
        c = CHORDS[s["chord"]]
        root, q = PCS[c["root"]], c["q"]
        fam = []
        for r in range(12):
            for qq in ["maj", "min"] + ([q] if q not in ("maj", "min") else []):
                tpl = template(r, QUAL[qq])
                fam.append((float(np.corrcoef(ch, tpl)[0, 1]), r, qq))
        fam.sort(key=lambda z: -z[0])
        labels = [chord_label(r, qq) for _, r, qq in fam]
        exp_label = chord_label(root, q)
        rank = labels.index(exp_label) + 1
        tri_q = "min" if q in ("min", "m7", "m9") else "maj"
        tri = [z for z in fam if z[2] in ("maj", "min")]
        tri_labels = [chord_label(r, qq) for _, r, qq in tri]
        tri_rank = tri_labels.index(chord_label(root, tri_q)) + 1
        score = fam[rank - 1][0]
        runner = fam[1] if rank == 1 else fam[0]
        rows.append(dict(bar=s["bar"], t0=s["t0"], t1=s["t1"], chord=s["chord"], template=exp_label,
                         score=round(score, 3), rank_in_family=rank, family_size=len(fam),
                         best=labels[0], best_score=round(fam[0][0], 3),
                         runner_up=chord_label(runner[1], runner[2]), runner_up_score=round(runner[0], 3),
                         runner_up_same_root=bool(runner[1] == root),
                         triad=chord_label(root, tri_q) + (" (no 3rd)" if q == "sus4" else ""),
                         triad_rank_of_24=tri_rank, chroma=[round(float(v), 3) for v in ch]))
    return rows


def correlation_report(x):
    blk = int(0.1 * SR)
    rs = []
    for i in range(0, N - blk + 1, blk):
        L, R = x[0, i:i + blk], x[1, i:i + blk]
        if np.sqrt(np.mean(L ** 2 + R ** 2) / 2) < db(-60):
            continue
        r = np.corrcoef(L, R)[0, 1]
        rs.append(r)
    rs = np.array(rs)
    low = filt(x, "lowpass", 150, 4)
    side = 0.5 * (low[0] - low[1])
    mid = 0.5 * (low[0] + low[1])
    return dict(overall=round(float(np.corrcoef(x[0], x[1])[0, 1]), 3),
                median_100ms=round(float(np.median(rs)), 3), p05_100ms=round(float(np.percentile(rs, 5)), 3),
                min_100ms=round(float(rs.min()), 3), frac_blocks_above_0p2=round(float((rs > 0.2).mean()), 3),
                below_150hz_side_to_mid_db=round(float(10 * np.log10((side ** 2).sum() / (mid ** 2).sum()
                                                                        + 1e-20)), 1))


def click_scan(x, known, label):
    """High-pass transient scan: |HP(>9 kHz)| spikes vs 20 ms local RMS. Spikes not within
    [-2, +8] ms of a known event onset are reported as unexplained."""
    hp_ = filt(x, "highpass", 9000, 4)
    e = (hp_ ** 2).sum(axis=0)
    c = np.concatenate([[0.0], np.cumsum(e)])
    w1, w2, gap = 48, 960, 96                   # 1 ms centre, +-20 ms surround, +-2 ms guard
    i = np.arange(N)
    lo = lambda k: np.clip(k, 0, N)
    centre = (c[lo(i + w1 // 2)] - c[lo(i - w1 // 2)]) / w1
    before = (c[lo(i - gap)] - c[lo(i - w2)]) / (w2 - gap)
    after = (c[lo(i + w2)] - c[lo(i + gap)]) / (w2 - gap)
    ratio = 10 * np.log10((centre + 1e-14) / (np.maximum(before, after) + 1e-14))
    idx = np.flatnonzero((ratio > 15.0) & (centre > db(-80) ** 2))
    clusters = []
    for i in idx:
        if not clusters or i - clusters[-1][-1] > int(0.005 * SR):
            clusters.append([i])
        else:
            clusters[-1].append(i)
    known = np.array(sorted(known))
    unexplained = []
    for cl in clusters:
        t = cl[0] / SR
        if known.size and np.any((t - known >= -0.002) & (t - known <= 0.008)):
            continue
        unexplained.append(round(t, 4))
    bounds = sorted(set([s["t0"] for s in SEGS] + [a for _, a, _ in SECTIONS] + [GAP_START, DROP, FADE_END]))
    at_bounds = {}
    for b in bounds:
        i0, i1 = int((b - 0.003) * SR), int((b + 0.003) * SR)
        at_bounds[str(b)] = round(float(ratio[max(i0, 0):min(i1, N)].max()), 2) if i1 > i0 else 0.0
    return dict(signal=label, metric="dB of 1 ms HP(>9 kHz) energy over the louder +-20 ms side; "
                                     "spike if > 15 dB", spikes=len(clusters), unexplained=len(unexplained),
                unexplained_times=unexplained[:40], max_ratio_at_boundaries=at_bounds)


# --- plots ------------------------------------------------------------------------

SEQ = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
CAT = {"impact": "#2a78d6", "pop": "#eb6834", "land": "#1baf7a", "ui": "#eda100", "glass": "#e87ba4",
       "sweep": "#008300", "drum": "#4a3aa7"}
CAT_OF = {"impact": "impact", "impact-soft": "impact", "pop": "pop", "land": "land", "click": "ui",
          "snap": "ui", "tick": "ui", "enter": "ui", "key": "ui", "ui-open": "ui", "shimmer": "glass",
          "chime": "glass", "whoosh": "sweep", "whoosh-short": "sweep", "swoosh": "sweep",
          "riser": "sweep", "reverse-swell": "sweep", "downlifter": "sweep", "snare-roll": "drum"}


def mel_fb(n_fft, n_mels=128, fmin=40.0, fmax=16000.0):
    h2m = lambda f: 2595 * np.log10(1 + f / 700)
    m2h = lambda m: 700 * (10 ** (m / 2595) - 1)
    pts = m2h(np.linspace(h2m(fmin), h2m(fmax), n_mels + 2))
    freqs = np.fft.rfftfreq(n_fft, 1 / SR)
    fb = np.zeros((n_mels, freqs.size))
    for i in range(n_mels):
        l, c, r = pts[i], pts[i + 1], pts[i + 2]
        fb[i] = np.clip(np.minimum((freqs - l) / (c - l), (r - freqs) / (r - c)), 0, None)
    return fb, pts[1:-1]


def plot_spectrogram(y, ts, L, sec_loud, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", SEQ)
    mono = y.mean(axis=0)
    nfft, hop = 4096, 240
    f, tt, Z = signal.stft(mono, SR, window="hann", nperseg=nfft, noverlap=nfft - hop,
                           boundary=None, padded=False)
    fb, centers = mel_fb(nfft)
    M = 10 * np.log10(fb @ (np.abs(Z) ** 2) + 1e-14)
    vmax = np.percentile(M, 99.7)
    fig = plt.figure(figsize=(18, 9.5), dpi=110)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.35, 4, 1.5], hspace=0.06)
    ax0 = fig.add_subplot(gs[0])
    ax1 = fig.add_subplot(gs[1], sharex=ax0)
    ax2 = fig.add_subplot(gs[2], sharex=ax0)
    ink, ink2 = "#0b0b0b", "#52514e"
    # cue lanes
    lanes = list(CAT.keys())
    for c in SFX:
        cat = CAT_OF.get(c["type"], "ui")
        yv = lanes.index(cat)
        if "until" in c:
            ax0.plot([c["t"], c["until"]], [yv, yv], color=CAT[cat], lw=4, solid_capstyle="round")
        ax0.plot([c["t"]], [yv], marker="|", ms=12, mew=2, color=CAT[cat])
    ax0.set_yticks(range(len(lanes)))
    ax0.set_yticklabels(lanes, fontsize=8, color=ink2)
    ax0.set_ylim(-0.7, len(lanes) - 0.3)
    ax0.invert_yaxis()
    for s in SEGS:
        ax0.text(s["t0"] + 0.05, -0.55, s["chord"], fontsize=7.5, color=ink2, va="bottom")
    ax0.set_title("PecoFence trailer v3 - variant B soundtrack: cue lanes (color = cue family), mel "
                  "spectrogram, short-term loudness", fontsize=11, color=ink, loc="left")
    # spectrogram
    ax1.imshow(M, origin="lower", aspect="auto", cmap=cmap, vmin=vmax - 70, vmax=vmax,
               extent=[tt[0] + nfft / 2 / SR, tt[-1] + nfft / 2 / SR, 0, M.shape[0]])
    ticks_hz = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 16000]
    ax1.set_yticks([np.interp(h, centers, np.arange(len(centers))) for h in ticks_hz])
    ax1.set_yticklabels(["50", "100", "200", "500", "1k", "2k", "5k", "10k", "16k"], fontsize=8, color=ink2)
    ax1.set_ylabel("Hz (mel scale)", fontsize=9, color=ink2)
    # loudness
    ax2.plot(ts + 1.5, L, color="#2a78d6", lw=2, label="short-term loudness (3 s window, plotted at centre)")
    for name, a, b in SECTIONS:
        v = sec_loud[name]["short_term_mean_lufs"]
        ax2.plot([a, b], [v, v], color=ink2, lw=1.2, ls="--")
        ax2.text(a + 0.08, v + 0.6, f"{name} {v:.1f}", fontsize=7.5, color=ink2)
    ax2.set_ylim(-40, -4)
    ax2.set_ylabel("LUFS", fontsize=9, color=ink2)
    ax2.set_xlabel("time (s)", fontsize=9, color=ink2)
    ax2.legend(loc="lower left", fontsize=8, frameon=False)
    for ax in (ax0, ax1, ax2):
        for name, a, b in SECTIONS:
            ax.axvline(a, color="#383835", lw=0.8, alpha=0.7)
        ax.set_xlim(0, 30)
        ax.tick_params(colors=ink2, labelsize=8)
        for sp in ax.spines.values():
            sp.set_color("#c3c2b7")
    for name, a, b in SECTIONS:
        ax1.text(a + 0.06, M.shape[0] - 6, name, fontsize=9, color=ink, va="top")
    ax2.grid(axis="y", color="#e6e5e0", lw=0.6)
    plt.setp(ax0.get_xticklabels(), visible=False)
    plt.setp(ax1.get_xticklabels(), visible=False)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_chroma(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", SEQ)
    ink, ink2 = "#0b0b0b", "#52514e"
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(18, 7.5), dpi=110, sharex=True,
                                  gridspec_kw=dict(height_ratios=[3.2, 1.2], hspace=0.08))
    edges = [r["t0"] for r in rows] + [rows[-1]["t1"]]
    C = np.array([r["chroma"] for r in rows]).T
    ax.pcolormesh(edges, np.arange(13) - 0.5, C, cmap=cmap, vmin=0, vmax=1, shading="flat")
    for r in rows:
        c = CHORDS[r["chord"]]
        root = PCS[c["root"]]
        mid = 0.5 * (r["t0"] + r["t1"])
        for iv in QUAL[c["q"]]:
            pc = (root + iv) % 12
            ax.plot([mid], [pc], marker="o", ms=9, mfc="none" if pc != root else "#eb6834",
                    mec="#eb6834", mew=1.8)
        ax.text(mid, 12.0, f"{r['chord']}\nrank {r['rank_in_family']}/{r['family_size']}",
                ha="center", va="bottom", fontsize=7.5, color=ink)
        ax.axvline(r["t0"], color="#383835", lw=0.6, alpha=0.6)
    ax.set_yticks(range(12))
    ax.set_yticklabels(PC_NAMES, fontsize=8, color=ink2)
    ax.set_ylim(-0.5, 13.3)
    ax.set_title("Music-stem chroma per chord segment (blue = energy, normalized per segment); orange rings "
                 "= expected chord tones, filled = root", fontsize=10.5, color=ink, loc="left")
    mids = [0.5 * (r["t0"] + r["t1"]) for r in rows]
    ax2.plot(mids, [r["score"] for r in rows], "o", color="#2a78d6", ms=8,
             label="correlation with expected chord template")
    ax2.plot(mids, [r["runner_up_score"] for r in rows], "o", mfc="none", mec="#52514e", ms=8,
             label="best competing chord (24 triads + transpositions of the expected quality)")
    ax2.set_ylim(-0.1, 1.05)
    ax2.set_ylabel("Pearson r", fontsize=9, color=ink2)
    ax2.set_xlabel("time (s)", fontsize=9, color=ink2)
    ax2.legend(loc="lower left", fontsize=8, frameon=False)
    ax2.grid(axis="y", color="#e6e5e0", lw=0.6)
    for a in (ax, ax2):
        a.set_xlim(0, 30)
        a.tick_params(colors=ink2, labelsize=8)
        for sp in a.spines.values():
            sp.set_color("#c3c2b7")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# =============================================================================
# MAIN
# =============================================================================

IR_HALL = IR_PLATE = IR_ROOM = IR_SPLASH = None


def main():
    global IR_HALL, IR_PLATE, IR_ROOM, IR_SPLASH
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IR_HALL = make_ir(4.0, 2.8, 11, predelay=0.02, corr=0.35)
    IR_PLATE = make_ir(2.2, 1.3, 12, predelay=0.008, band_mult=(1.0, 1.0, 0.85, 0.6), corr=0.3)
    IR_ROOM = make_ir(1.0, 0.45, 13, predelay=0.004, corr=0.4)
    IR_SPLASH = make_ir(3.5, 2.2, 14, predelay=0.005, band_mult=(0.9, 1.0, 0.9, 0.7), corr=0.3)

    B, kicks = compose_music()
    mparts, monsets = process_music(B, kicks)
    music = sum(mparts.values()) * cue_duck()
    sparts = compose_sfx()
    sfx = sum(sparts.values())
    music = glue(music, sfx)
    print(f"rendered in {time.time() - t_start:.1f}s")

    y, lim_gain, gdb, ceiling, stems = master(music, sfx)
    # write
    sf.write(OUT_DIR / "soundtrack.wav", y.T, SR, subtype="PCM_24")
    for name, s in stems.items():
        sub = "PCM_24" if np.max(np.abs(s)) < 0.999 else "FLOAT"
        sf.write(OUT_DIR / f"{name}.wav", s.T, SR, subtype=sub)
    # re-read quantized master for the report
    yq, _ = sf.read(OUT_DIR / "soundtrack.wav", always_2d=True)
    yq = yq.T
    meter = pyln.Meter(SR)
    lufs = meter.integrated_loudness(yq.T)
    tp = true_peak_db(yq, 4)
    tp8 = true_peak_db(yq, 8)
    sec_loud, ts, Lst = section_loudness(yq)
    onsets, det = onset_report(stems["sfx"])
    chords = chord_report(stems["music"])
    corr = correlation_report(yq)
    sfx_known = [c["t"] for c in SFX] + [t for c in SFX if c["type"] == "snare-roll"
                                          for t in snare_roll_times(c["t"], c["until"])] + \
        [c["t"] + 0.028 for c in SFX if c["type"] == "snap"] + \
        [c["t"] + 0.075 * k for c in SFX if c["type"] == "chime" for k in range(4)]
    tonal = sum(v for k, v in mparts.items() if k in ("pad", "ep", "arp", "sub", "bass", "stab", "lead"))
    clicks = [click_scan(tonal * end_fade(), monsets, "music tonal buses (pad/ep/arp/bass/stab/lead)"),
              click_scan(yq, monsets + sfx_known, "master")]
    req = [r for r in onsets if r["required"]]
    errs = [abs(r["error_ms"]) for r in req if r["error_ms"] is not None]
    st_means = {k: v["short_term_mean_lufs"] for k, v in sec_loud.items()}
    report = dict(
        variant="B - warm melodic future pop",
        file=str(OUT_DIR / "soundtrack.wav"),
        format=dict(sr=SR, channels=int(yq.shape[0]), samples=int(yq.shape[1]), subtype="PCM_24"),
        integrated_lufs=round(float(lufs), 2),
        true_peak_dbtp_4x=round(float(tp), 2),
        true_peak_dbtp_8x=round(float(tp8), 2),
        sample_peak_dbfs=round(float(20 * np.log10(np.max(np.abs(yq)) + 1e-12)), 2),
        clipped_samples=int(np.sum(np.abs(yq) >= 0.99999)),
        dc_offset=[float(f"{v:.2e}") for v in yq.mean(axis=1)],
        master_gain_db=round(float(gdb), 2), limiter_ceiling_dbtp=round(ceiling, 2),
        limiter_max_gain_reduction_db=round(float(-20 * np.log10(lim_gain.min())), 2),
        limiter_gr_over_1db_seconds=round(float((lim_gain < db(-1)).sum() / SR), 3),
        gap_19p94_20p0_peak_dbfs=round(float(20 * np.log10(np.max(np.abs(
            yq[:, int(GAP_START * SR) + 1:int(DROP * SR)])) + 1e-12)), 1),
        tail_29p8_30p0_all_zero=bool(np.all(yq[:, int(FADE_END * SR):] == 0.0)),
        sections=sec_loud,
        drop_is_loudest=bool(max(st_means, key=st_means.get) == "drop"),
        intro_is_quietest=bool(min(st_means, key=st_means.get) == "intro"),
        onsets=onsets,
        onset_max_abs_error_ms_required=round(float(max(errs)) if errs else -1, 2),
        onset_missing_required=sum(1 for r in req if r["error_ms"] is None),
        chords=chords,
        chords_all_rank1=all(r["rank_in_family"] == 1 for r in chords),
        lr_correlation=corr,
        cue_salience_sfx_over_music_db=cue_salience(stems["music"], stems["sfx"]),
        click_scan=clicks,
        render_seconds=round(time.time() - t_start, 1),
        notes=("Onsets: energy-ratio detector on the 250 Hz high-passed sfx stem (1 ms trailing window vs "
               "previous 10 ms, +9 dB); keys are reported but not required. Chord family: 24 major/minor "
               "triads plus the 12 transpositions of the expected chord quality; templates weight the root "
               "1.5 and other chord tones 1.0; chroma = sqrt semitone-band energy C2..E7 of the harmonic part "
               "(median-filter HPSS, STFT 16384/2048) of the music stem, frames centred inside the segment. "
               "Section short-term loudness = energy mean of 3 s windows lying fully inside the section."),
    )
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    plot_spectrogram(yq, ts, Lst, sec_loud, OUT_DIR / "spectrogram.png")
    plot_chroma(chords, OUT_DIR / "chroma.png")
    print(json.dumps({k: report[k] for k in ["integrated_lufs", "true_peak_dbtp_4x", "true_peak_dbtp_8x",
                                             "sample_peak_dbfs", "limiter_max_gain_reduction_db",
                                             "onset_max_abs_error_ms_required", "onset_missing_required",
                                             "chords_all_rank1", "drop_is_loudest", "intro_is_quietest",
                                             "render_seconds"]}, indent=1))
    print(json.dumps(sec_loud, indent=1))


if __name__ == "__main__":
    main()
