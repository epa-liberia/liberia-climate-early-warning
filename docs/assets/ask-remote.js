/* Public site only: sends a visitor's question, with the platform facts the page found for it, to EPA's
   Google Apps Script, which asks the AI and returns the answer. The AI key stays in EPA's Google account. */
(function () {
  var url = String(window.LM_ASK_URL || '').trim();
  if (!/^https:\/\/script\.google(usercontent)?\.com\//.test(url)) { window.LM_ASK_REMOTE = null; return; }
  window.LM_ASK_REMOTE = {
    enabled: true,
    ask: function (payload) {
      var ctl = new AbortController(); var t = setTimeout(function () { ctl.abort(); }, 30000);
      // text/plain keeps this a simple request, which Apps Script web apps accept from any site.
      return fetch(url, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(payload), signal: ctl.signal })
        .then(function (r) { return r.json(); })
        .then(function (j) { clearTimeout(t); if (!j || !j.ok) { var e = new Error((j && j.error) || 'failed'); e.code = j && j.code; throw e; } return j; },
              function (e) { clearTimeout(t); throw e; });
    }
  };
})();
