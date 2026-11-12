"""Check the data files and stamp the ones that changed in docs/data/manifest.json.
Usage: python3 scripts/update_manifest.py   (run from the repository root)"""
import json, hashlib, pathlib, datetime, sys
root = pathlib.Path(__file__).resolve().parent.parent
mp = root / "docs" / "data" / "manifest.json"
man = json.loads(mp.read_text(encoding="utf-8"))
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
MIN_ROWS = {"nino_regions": 4, "outlook": 6, "roni": 30, "enso_status": 1, "fao_county": 15, "county_watch": 15}
bad = []
for k, e in man.items():
    f = root / "docs" / e["file"]
    raw = f.read_bytes()
    try:
        obj = json.loads(raw)
    except Exception as ex:
        bad.append(f"{k}: not valid JSON ({ex})"); continue
    if k in MIN_ROWS and (not isinstance(obj, list) or len(obj) < MIN_ROWS[k]):
        bad.append(f"{k}: expected at least {MIN_ROWS[k]} rows")
    sha = hashlib.sha256(raw).hexdigest()[:16]
    if e.get("sha") != sha:
        if e.get("sha"): e["updated"] = now
        e["sha"] = sha
if bad:
    print("Data check failed; not saving:\n" + "\n".join(bad)); sys.exit(1)
mp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
print("manifest ok")
