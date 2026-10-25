// 1.4 收起与展开: double-click the title to roll up (count "8 项", chevron turns), hover the
// rolled title to peek it open, leave to roll back, click the chevron to keep it open.
(() => {
    'use strict';
    const { E, ramp, lerp, inside, pathAt, firstWhen, spans, spanFade, el, put, local, icon, fence,
        placeFence, pointer, drawPointer, taskbar, loopFade, T } = PM;

    const D = 10.2;
    const P0 = { x: 105, y: 60, w: 168, h: 204 };
    const F0 = { x: 293, y: 60, w: 402, h: 204 };
    const ROLLED_H = 32, HOVER_DELAY = .4;
    const CHEV = { x: F0.x + F0.w - 4 - 32, y: F0.y, w: 32, h: 32 };
    const TITLE = { x: F0.x, y: F0.y, w: F0.w, h: 32 };

    const PATH = [
        [0, 600, 380], [0.3, 600, 380],
        [1.0, 440, 76], [1.6, 440, 76],          // double-click the title
        [2.3, 600, 330], [3.2, 600, 330],
        [3.8, 470, 76], [4.6, 470, 76],          // rest on the rolled title
        [5.2, 470, 190], [5.6, 470, 190],        // into the content: stays open
        [6.3, 690, 385], [6.9, 690, 385],        // leave: rolls back
        [7.6, CHEV.x + 16, CHEV.y + 16], [8.6, CHEV.x + 16, CHEV.y + 16],
        [9.3, 560, 360], [D, 560, 360],
    ];
    const DBL = [1.25, 1.42], CHEV_CLICK = 7.85;
    const at = t => pathAt(t, PATH);

    // Roll transitions [start, target (1 = rolled), seconds]: up 167 ms, down 333 ms (slowed a
    // little so the motion reads).
    const hoverIn = firstWhen(3.2, 4.6, t => inside(at(t), TITLE));
    const hoverOpen = hoverIn + HOVER_DELAY;
    const leave = firstWhen(5.6, 6.9, t => !inside(at(t), F0));
    const EVENTS = [[DBL[1] + .03, 1, .22], [hoverOpen, 0, .36], [leave + .12, 1, .22], [CHEV_CLICK + .03, 0, .36]];
    const rollAt = t => {
        let v = 0;
        for (const [te, to, d] of EVENTS) {
            if (t < te) break;
            v = lerp(v, to, ramp(t, te, te + d, E.p2p));
        }
        return v;
    };

    const CLICKS = [{ t: DBL[0] }, { t: DBL[1] }, { t: CHEV_CLICK }];
    const CHIPS = [[1.15, 1.75, '双击标题栏', 16, -34], [hoverIn, hoverOpen, '停一下'], [7.62, 8.15, '点箭头', -54, -44]];

    function build(root) {
        const r = {};
        el('div', 'wall', root);
        r.scene = el('div', 'scene', root);
        const S = r.scene;
        r.P = fence(S, { ...P0, title: '程序' });
        r.F = fence(S, { ...F0, title: '文件与文档' });
        [['url', '项目主页'], ['exe', '截图工具'], ['url', '在线文档'], ['exe', '录屏']]
            .forEach(([k, l], i) => {
                const s = local(i, 2);
                put(icon(r.P.body, k, l), s.x, s.y);
            });
        [['pdf', '合同.pdf'], ['docx', '周报.docx'], ['xlsx', '预算.xlsx'], ['txt', '待办.txt'], ['pdf', '发票.pdf'],
            ['docx', '方案.docx'], ['xlsx', '报价单.xlsx'], ['folder', '素材']]
            .forEach(([k, l], i) => {
                const s = local(i, 5);
                put(icon(r.F.body, k, l), s.x, s.y);
            });
        r.F.count.textContent = T('{0} 项').replace('{0}', '8');
        r.ptr = pointer(S);
        taskbar(root);
        r.titleHover = spans(D, t => inside(at(t), TITLE));
        r.chevHover = spans(D, t => inside(at(t), CHEV));
        return r;
    }

    function render(t, r, { looped }) {
        r.scene.style.opacity = loopFade(t, D, looped);
        const p = at(t);
        const roll = rollAt(t);
        placeFence(r.F, F0.x, F0.y, F0.w, lerp(F0.h, ROLLED_H, roll));
        r.F.body.style.opacity = 1 - roll;

        // title row: hover pill, rolled count, chevron (always shown while rolled or rolling)
        const hover = spanFade(t, r.titleHover);
        r.F.pill.style.opacity = hover;
        r.F.count.style.opacity = roll;
        r.F.chev.style.opacity = roll > 0 ? Math.max(.75, hover) : hover;
        r.F.chev.firstChild.style.transform = `rotate(${180 * roll}deg)`;
        r.F.chev.classList.toggle('hot', spanFade(t, r.chevHover) > .5);

        drawPointer(r.ptr, t, p, { clicks: CLICKS, chips: CHIPS, at });
    }

    PM.register('roll', { duration: D, poster: 2.6, build, render });
})();
