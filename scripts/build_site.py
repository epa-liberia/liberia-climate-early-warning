"""Build the public site page from the shared page source.
Usage: python3 build_site.py   (run from the repository root)
Reads page/index.html (the same file the Claude version uses) and writes docs/index.html."""
import re, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
src = (root / "page" / "index.html").read_text(encoding="utf-8")
src = src.replace('<meta name="dash-one-writer">', "")
# Images stored as Claude artifact assets are served from docs/assets on the public site.
ASSETS = {"/_blob/4eb17e335402b27d0e7debfd176f5a11": "assets/epa-logo.png", "/_blob/7053b1572da21a0b5e95e4aeda693159": "assets/liberia-seal.png"}
for k, v in ASSETS.items(): src = src.replace(k, v)
assert "/_blob/" not in src, "page uses an artifact asset with no public copy; add it to ASSETS"
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
</body>
</html>
"""
(root / "docs" / "index.html").write_text(head + src + foot, encoding="utf-8")
print("wrote docs/index.html", len(head + src + foot))
