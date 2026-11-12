"""Build the public site page from the shared page source.
Usage: python3 build_site.py   (run from the repository root)
Reads page/index.html (the same file the Claude version uses) and writes docs/index.html."""
import re, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
src = (root / "page" / "index.html").read_text(encoding="utf-8")
src = src.replace('<meta name="dash-one-writer">', "")
# Each page script runs in its own scope on claude.ai; keep that here.
src = re.sub(r"<script>(.*?)</script>", lambda m: "<script>(function () {\n" + m.group(1) + "\n})();</script>", src, flags=re.S)
head = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Liberia El Niño Early Warning Platform · EPA Liberia</title>
<meta name="description" content="El Niño monitoring, hazard maps, drought and crop stress, and preparedness for Liberia. Environmental Protection Agency of Liberia.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Source+Serif+4:wght@400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/theme.css">
<script src="assets/d3.min.js"></script>
<script src="assets/dash-runtime.js"></script>
</head>
<body>
<div id="dash-root" lang="en">
"""
foot = """
</div>
<details class="pub-sources" id="pub-sources"><summary>Data sources and when each was last updated</summary><table><thead><tr><th>Source</th><th>What it is</th><th>Updated (UTC)</th><th>Download</th></tr></thead><tbody></tbody></table></details>
<script>
dash.manifest().then(function (m) {
  var tb = document.querySelector('#pub-sources tbody');
  Object.keys(m).sort(function (a, b) { return (m[a].title || a).localeCompare(m[b].title || b); }).forEach(function (k) {
    var e = m[k], tr = document.createElement('tr');
    [e.title || k, e.description || '', (e.updated || '').replace('T', ' ').slice(0, 16)].forEach(function (t) { var td = document.createElement('td'); td.textContent = t; tr.appendChild(td); });
    var td = document.createElement('td'), a = document.createElement('a'); a.href = e.file; a.textContent = 'JSON'; a.setAttribute('download', ''); td.appendChild(a); tr.appendChild(td);
    tb.appendChild(tr);
  });
});
</script>
</body>
</html>
"""
(root / "docs" / "index.html").write_text(head + src + foot, encoding="utf-8")
print("wrote docs/index.html", len(head + src + foot))
