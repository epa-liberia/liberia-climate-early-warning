/* Liberia El Niño Early Warning Platform — standalone runtime.
   Implements the small part of the Claude dashboard API the page uses (dash.data, dash.calc, dash.draw,
   dash.onData, dash.setLink), so the same page code runs on claude.ai and on any static web host.
   Data files are listed in data/manifest.json and loaded only when a visible part of the page needs them. */
(function () {
  'use strict';
  const DS = {}, CALCS = {}, CALC_CACHE = {}, DRAWS = {}, ORDER = [], ONDATA = [];
  const MADE = new WeakMap();
  let manifest = null, scheduled = false, started = false;
  const manifestP = fetch('data/manifest.json', { cache: 'no-cache' }).then((r) => r.json()).then((m) => { manifest = m; return m; })
    .catch((e) => { console.error('manifest', e); manifest = {}; return {}; });

  function schedule() {
    if (scheduled || !started) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; runAll(); });
  }
  function load(id) {
    if (DS[id]) return DS[id];
    const s = { status: 'loading', data: [], columns: [], message: null };
    DS[id] = s;
    manifestP.then((m) => {
      const e = m[id];
      if (!e) { s.status = 'missing'; schedule(); return; }
      const v = e.updated ? ('?v=' + encodeURIComponent(e.updated)) : '';
      return fetch(e.file + v).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then((j) => { s.data = j; s.status = 'ok'; if (Array.isArray(j) && j.length && typeof j[0] === 'object') s.columns = Object.keys(j[0]); schedule(); })
        .catch((err) => { s.status = 'error'; s.message = String(err); s.data = []; schedule(); });
    });
    return s;
  }
  function calc(id) {
    const c = CALCS[id];
    const ins = c.inputs.map((i) => data(i));
    const bad = ins.find((d) => d.status !== 'ok');
    if (bad) return { status: bad.status === 'loading' ? 'loading' : 'error', data: null, message: bad.message || null, refreshing: false, meta: null };
    const key = ins.map((d) => d.data);
    const prev = CALC_CACHE[id];
    if (prev && prev.key.length === key.length && prev.key.every((k, i) => k === key[i])) return prev.result;
    let result;
    try {
      const args = ins.map((d) => d.data);
      result = { status: 'ok', data: c.fn(...args), message: null, refreshing: false, meta: null };
    } catch (e) { console.error('calc ' + id, e); result = { status: 'error', data: null, message: String(e), refreshing: false, meta: null }; }
    CALC_CACHE[id] = { key, result };
    return result;
  }
  function data(id) {
    if (CALCS[id]) return calc(id);
    const s = load(id);
    return { status: s.status, data: s.data, columns: s.columns, message: s.message, refreshing: false, meta: null };
  }
  function visible(el) { return el.isConnected && !el.closest('[hidden]'); }
  function runOne(name, el) {
    const d = DRAWS[name];
    if (!d || !visible(el)) return;
    try {
      if (typeof d === 'function') d(el);
      else {
        let made = MADE.get(el);
        if (made === undefined && d.mount) { el.replaceChildren(); made = d.mount(el); MADE.set(el, made); }
        if (d.update) d.update(el, made);
      }
    } catch (e) { console.error('draw ' + name, e); }
  }
  function runName(name) { document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => runOne(name, el)); }
  function runAll() {
    ONDATA.forEach((fn) => { try { fn(); } catch (e) { console.error('onData', e); } });
    ORDER.forEach(runName);
  }
  window.dash = {
    data,
    calc(id, spec) { CALCS[id] = { inputs: spec.inputs || [], fn: spec.fn, title: spec.title, description: spec.description }; },
    loader() {},
    draw(name, spec) {
      if (spec === undefined) { runName(name); return; }
      if (!DRAWS[name]) ORDER.push(name);
      DRAWS[name] = spec;
      schedule();
    },
    onData(fn) { ONDATA.push(fn); try { fn(); } catch (e) { console.error('onData', e); } },
    refresh(id) { delete DS[id]; schedule(); },
    setLink(name) { try { history.replaceState(null, '', '#' + name); } catch (e) { /* ignore */ } },
    params() { return {}; }, setParams() {}, resetParams() {},
    colors: ['#002868', '#BF0A30', '#8a94a6', '#E3A008', '#2f9e44', '#7048e8'],
    manifest: () => manifestP
  };
  function start() {
    started = true;
    runAll();
    // Redraw only when a section is shown or hidden, not when a drawing changes its own contents (such as a tooltip).
    const affectsDrawings = (m) => {
      const t = m.target;
      if (m.attributeName !== 'hidden' || t.nodeType !== 1) return false;
      if (t.parentElement && t.parentElement.closest('[data-draw]')) return false;
      return t.hasAttribute('data-draw') || !!t.querySelector('[data-draw]');
    };
    new MutationObserver((muts) => { if (muts.some(affectsDrawings)) schedule(); })
      .observe(document.body, { attributes: true, attributeFilter: ['hidden'], subtree: true });
    let lastW = document.documentElement.clientWidth;
    new ResizeObserver(() => { const w = document.documentElement.clientWidth; if (w !== lastW) { lastW = w; schedule(); } }).observe(document.documentElement);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else setTimeout(start, 0);
})();
