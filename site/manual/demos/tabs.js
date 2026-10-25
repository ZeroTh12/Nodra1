// 3.1 标签页: drag 灵感 by its title onto 项目's title row (the title row lights up and a white
// outline marks the window it will join) → it becomes the active tab of 项目's window; a click
// on a tab and Ctrl+Tab switch pages (old content fades out, new content fades in sliding from
// the new tab's side, the selection glides); dragging the tab 28 DIP out of the row tears it
// off into its own fence under the pointer.
(() => {
    'use strict';
    const { E, ramp, lerp, inside, pathAt, firstWhen, spans, spanFade, el, put, size, show, local, icon, fence,
        pointer, drawPointer, drawKeys, taskbar, loopFade, T, TITLE_H } = PM;

    const D = 11.5;
    const A = { x: 40, y: 48, w: 402, h: 236 };       // 项目: the window both end up in
    const B0 = { x: 520, y: 200, w: 246, h: 204 };    // 灵感
    const GRAB = { x: 40, y: 10 };                     // where 灵感's title is held
    // Strip geometry (fence_window/consts.rs, tabs.rs tab_natural_widths): TAB_LEFT 8, TAB_GAP 4;
    // a pill is its caption + 16 clamped to 48..160, measured in build so any language fits
    // (both two-character zh-CN tabs are 48 wide). The accent bar is 20 wide (fence_chrome.rs).
    const TAB_LEFT = 8, TAB_GAP = 4, TAB_PAD = 16, TAB_MIN = 48, TAB_MAX = 160, MARK_W = 20;
    let TEXT_W = [26, 26], TAB_W = [TAB_MIN, TAB_MIN], TAB_X = [TAB_LEFT, TAB_LEFT + TAB_MIN + TAB_GAP];   // 项目, 灵感
    const TAB_DETACH = 28;
    // Real timings, slowed a touch so they read: content 83 ms fades, 167 ms slide and
    // selection glide; merge hint 83 ms in / 167 ms out; exit / entrance 167 ms (+ 250 ms scale).
    const FADE = .11, SLIDE = .22, GLIDE = .22, HINT_IN = .083, HINT_OUT = .167;
    const EXIT = .2, ENTER = .2, ENTER_SCALE = .3, NEW_TAB = .1, SLIDE_DIP = 24;

    const PRESS1 = 1.2, MERGE_AT = 2.75;               // 灵感's title held … released over 项目
    // the merged fence holds still for 0.9 s so step 2 can be read
    const CLICK1 = 4.6, CTRL_AT = 5.9;                 // click 项目, then Ctrl+Tab back to 灵感
    const PRESS2 = 7.3, RELEASE2 = 8.9;                // hold 灵感's tab … drop the torn-off fence
    // The pointer aims 3 px past the caption's end (inside the pill), so the caption stays visible.
    const aim = i => A.x + TAB_X[i] + (TAB_W[i] + Math.min(TEXT_W[i], TAB_W[i] - 16)) / 2 + 3;
    let PATH, TEAR_AT, CHIPS;   // depend on the measured tabs: set by plan() in build
    function plan() {
        PATH = [
            [0, 640, 392], [0.3, 640, 392],
            [1.0, B0.x + GRAB.x, B0.y + GRAB.y], [PRESS1, B0.x + GRAB.x, B0.y + GRAB.y],
            [1.75, 556, 70],                                // up to the height of 项目's title row
            [2.5, 290, 70], [3.7, 290, 70],                 // along it: 项目's title lights up
            [4.4, aim(0), 64], [4.7, aim(0), 64],
            [5.3, 250, 186], [6.6, 250, 186],
            [7.1, aim(1), 64], [PRESS2, aim(1), 64],
            [7.65, aim(1) + 4, 102],                        // down out of the title row
            [8.7, 610, 150], [9.0, 610, 150],
            [9.7, 664, 382], [D, 664, 382],
        ];
        TEAR_AT = firstWhen(PRESS2, RELEASE2, t => at(t).y - at(PRESS2).y > TAB_DETACH);
        // 点标签 sits 8 px after the strip's end
        const tip = A.x + TAB_X[1] + TAB_W[1] + 8 - aim(0);
        CHIPS = [[PRESS1, 2.45, '按住标题栏拖动'], [4.35, 4.62, '点标签', tip, -11], [PRESS2, 8.45, '拖出标题栏', 16, -34]];
    }
    const at = t => pathAt(t, PATH);
    const TITLE_ROW = { x: A.x, y: A.y, w: A.w, h: TITLE_H };
    const CLICKS = [{ t: CLICK1 }];
    const PRESSES = [[PRESS1, MERGE_AT], [PRESS2, RELEASE2]];

    // Caption width as drawn (the stage's font for this language); canvas, so it works even
    // while the stage is not laid out yet.
    const ctx2d = document.createElement('canvas').getContext('2d');
    function textWidth(n) {
        const cs = getComputedStyle(n);
        ctx2d.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
        return ctx2d.measureText(n.textContent).width;
    }
    const KEYS = [{ a: 5.6, b: 6.35, keys: ['Ctrl', 'Tab'], down: CTRL_AT }];
    // Page switches in 项目's window: [time, page shown, direction] (+1 = the new tab is to the
    // right, so its content comes in from the right). The merge and the tear-off swap content
    // without the animation, like the app (only a switch between two existing tabs slides).
    const SWITCHES = [[CLICK1, 0, -1], [CTRL_AT, 1, 1]];

    // Where 灵感's window is and how it shows: dragged by its title, fading out (Direct Exit)
    // once merged, then re-created under the pointer when its tab is torn off (Direct Entrance:
    // centred on the pointer, title row under it) and carried to its new place.
    function bWindow(t) {
        if (t < PRESS1) return { ...B0, o: 1, s: 1 };
        if (t < MERGE_AT) {
            const p = at(t);
            return { ...B0, x: p.x - GRAB.x, y: p.y - GRAB.y, o: 1, s: 1 };
        }
        if (t < TEAR_AT) {
            const p = at(MERGE_AT), q = ramp(t, MERGE_AT, MERGE_AT + EXIT, E.lin);
            return { ...B0, x: p.x - GRAB.x, y: p.y - GRAB.y, o: 1 - q, s: lerp(1, .97, ramp(t, MERGE_AT, MERGE_AT + EXIT)) };
        }
        const p = at(Math.min(t, RELEASE2));
        return {
            ...B0, x: p.x - B0.w / 2, y: p.y - TITLE_H / 2,
            o: ramp(t, TEAR_AT, TEAR_AT + ENTER, E.lin), s: lerp(.97, 1, ramp(t, TEAR_AT, TEAR_AT + ENTER_SCALE)),
        };
    }

    const stripOn = t => t >= MERGE_AT && t < TEAR_AT;
    // Active tab of 项目's window: 0 = 项目, 1 = 灵感 (attach_tab makes the joining fence active).
    function activeTab(t) {
        let a = 1;
        for (const [ts, page] of SWITCHES) if (t >= ts) a = page;
        return a;
    }

    function build(root) {
        const r = {};
        el('div', 'wall', root);
        r.scene = el('div', 'scene', root);
        const S = r.scene;
        r.A = fence(S, { ...A, title: '项目' });
        r.outline = el('div', 'tabs-outline', S);
        r.B = fence(S, { ...B0, title: '灵感' });

        const docs = [['pdf', '合同.pdf'], ['docx', '周报.docx'], ['xlsx', '预算.xlsx'], ['docx', '方案.docx'],
            ['txt', '待办.txt'], ['pdf', '发票.pdf'], ['folder', '素材']];
        const thumbs = [['atelier', 'Atelier.png'], ['form', 'Form.png'], ['sol', 'Sol.png'], ['still', 'Still.png'],
            ['terra', 'Terra.png'], ['tide', 'Tide.png']];
        r.pages = [el('div', 'tabs-panel', r.A.body), el('div', 'tabs-panel', r.A.body)];
        docs.forEach(([k, l], i) => {
            const s = local(i, 5);
            put(icon(r.pages[0], k, l), s.x, s.y);
        });
        thumbs.forEach(([k, l], i) => {
            const s = local(i, 5);
            put(icon(r.pages[1], `assets/icons/tabs-${k}.png`, l), s.x, s.y);
            const b = local(i, 3);
            put(icon(r.B.body, `assets/icons/tabs-${k}.png`, l), b.x, b.y);
        });

        // 项目's title row: merge hint, then the tab strip (hover fills, selection, captions)
        r.merge = el('div', 'tabs-merge', r.A.bar);
        r.A.bar.insertBefore(r.merge, r.A.name);
        r.strip = el('div', 'tabs-strip', r.A.bar);
        r.hov = [0, 1].map(() => el('div', 'tabs-hov', r.strip));
        r.sel = el('div', 'tabs-sel', r.strip);
        r.mark = el('div', 'tabs-mark', r.strip);
        r.caps = ['项目', '灵感'].map(s => el('div', 'tabs-cap', r.strip, s));
        TEXT_W = r.caps.map(textWidth);
        TAB_W = TEXT_W.map(w => Math.min(TAB_MAX, Math.max(TAB_MIN, w + TAB_PAD)));
        TAB_X = [TAB_LEFT, TAB_LEFT + TAB_W[0] + TAB_GAP];
        r.caps.forEach((n, i) => {
            n.style.width = TAB_W[i].toFixed(2) + 'px';
            put(n, TAB_X[i], 0);
        });
        r.hov.forEach((n, i) => {
            n.style.width = TAB_W[i].toFixed(2) + 'px';
            put(n, TAB_X[i], 0, 0);
        });
        plan();

        r.keys = el('div', 'keys', S);
        r.ptr = pointer(S);
        taskbar(root);

        r.hintSpans = spans(D, t => t >= PRESS1 && t < MERGE_AT && inside(at(t), TITLE_ROW));
        r.tabHover = TAB_X.map((x, i) => spans(D, t => stripOn(t) && activeTab(t) !== i && (t < PRESS2 || t >= TEAR_AT)
            && inside(at(t), { x: A.x + x, y: A.y + 5, w: TAB_W[i], h: 22 })));
        return r;
    }

    function render(t, r, { looped }) {
        r.scene.style.opacity = loopFade(t, D, looped);
        const p = at(t);

        // 灵感's own window
        const b = bWindow(t);
        if (show(r.B.n, b.o > 0)) {
            size(r.B.n, b.w, b.h);
            put(r.B.n, b.x, b.y, b.o, b.s !== 1 ? ` scale(${b.s.toFixed(4)})` : '');
            // its icons are already on 项目's 灵感 page: only the empty glass fades out
            show(r.B.body, t < MERGE_AT || t >= TEAR_AT);
        }

        // merge target feedback: the title row wash (83 ms in, 167 ms out) and the outline
        r.merge.style.opacity = spanFade(t, r.hintSpans, HINT_IN, HINT_OUT);
        const outlined = r.hintSpans.some(([s, e]) => t >= s && t < e);
        if (show(r.outline, outlined)) {
            size(r.outline, A.w, A.h);
            put(r.outline, A.x, A.y);
        }

        // title row: a plain title, or the strip while 灵感 is one of its tabs
        const strip = stripOn(t);
        show(r.A.name, !strip);
        if (show(r.strip, strip)) {
            const active = activeTab(t);
            // the selection fill and its accent bar glide to the new tab (167 ms decelerate),
            // the fill taking the new pill's width on the way
            let x = TAB_X[1], w = TAB_W[1];
            for (const [ts, page] of SWITCHES) {
                if (t < ts) break;
                const q = ramp(t, ts, ts + GLIDE);
                x = lerp(x, TAB_X[page], q);
                w = lerp(w, TAB_W[page], q);
            }
            const join = ramp(t, MERGE_AT, MERGE_AT + NEW_TAB, E.lin);   // the new pill fades in
            const selA = active === 1 && t < CLICK1 ? join : 1;
            size(r.sel, w, 22);
            put(r.sel, x, 0, selA);
            put(r.mark, x + (w - MARK_W) / 2, 0, selA);
            r.caps.forEach((n, i) => {
                n.classList.toggle('on', i === active);
                n.classList.toggle('pressed', i === 1 && t >= PRESS2 && t < TEAR_AT);
                n.style.opacity = i === 1 ? join : 1;
            });
            r.hov.forEach((n, i) => {
                n.style.opacity = spanFade(t, r.tabHover[i]);
            });
        }

        // pages in 项目's body: Direct Exit / Entrance on a tab switch, a plain swap otherwise
        const shown = strip ? activeTab(t) : 0;
        const last = strip ? SWITCHES.filter(([ts]) => t >= ts).pop() : null;
        r.pages.forEach((n, i) => {
            let o = i === shown ? 1 : 0, dx = 0;
            if (last) {
                const [ts, page, dir] = last;
                if (i === page) {
                    o = ramp(t, ts, ts + FADE, E.lin);
                    dx = dir * SLIDE_DIP * (1 - ramp(t, ts, ts + SLIDE));
                } else {
                    o = 1 - ramp(t, ts, ts + FADE, E.lin);
                }
            }
            if (show(n, o > 0)) put(n, dx, 0, o);
        });

        drawKeys(r.keys, t, KEYS);
        drawPointer(r.ptr, t, p, { clicks: CLICKS, presses: PRESSES, chips: CHIPS, at });
    }

    PM.register('tabs', { duration: D, poster: 6.55, build, render });
})();
