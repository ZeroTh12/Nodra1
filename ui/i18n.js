// Shared catalog keys match crates/core/src/i18n.rs. No network requests at runtime.
(() => {
  let locale = 'zh-CN', messages = {};
  // A key may start with a gettext-style context ending in U+0004 (see crates/core/src/i18n.rs).
  const bare = source => source.slice(source.indexOf('\x04') + 1);
  const text = source => locale === 'zh-CN' ? bare(source) : (messages[source] ?? bare(source));
  const format = (source, ...args) => text(source).replace(/\{(\d+)\}/g,
    (match, index) => index < args.length ? String(args[index]) : match);
  const set = (tag, catalog) => {
    const changed = locale !== tag;
    locale = tag || 'zh-CN';
    messages = catalog || {};
    document.documentElement.lang = locale;
    return changed;
  };
  // Capture only the original document. Later user-provided titles, filenames,
  // snapshot names and rule values must never be treated as translation keys.
  const capture = root => {
    const bindings = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.parentElement?.closest('script,style,[data-language-name]')) continue;
      const original = node.nodeValue, source = original.trim();
      if (!/[\u3400-\u9fff]/.test(source)) continue;
      const target = node;
      bindings.push(() => { target.nodeValue = original.replace(source, text(source)); });
    }
    // Non-Chinese source text such as units names its message explicitly.
    for (const el of root.querySelectorAll('[data-i18n]')) {
      bindings.push(() => { el.textContent = text(el.dataset.i18n); });
    }
    for (const el of root.querySelectorAll('[title],[placeholder],[aria-label]')) {
      for (const attr of ['title', 'placeholder', 'aria-label']) {
        const source = el.getAttribute(attr);
        if (source && /[\u3400-\u9fff]/.test(source)) {
          bindings.push(() => el.setAttribute(attr, text(source)));
        }
      }
    }
    return () => bindings.forEach(apply => apply());
  };
  window.PecoFenceI18n = { text, format, set, capture };
  const initial = window.PECOFENCE_LOCALE;
  if (initial) set(initial.locale, initial.translations);
})();
