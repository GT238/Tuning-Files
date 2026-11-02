#!/usr/bin/env python3
"""
build_catalog.py -- generate a static, searchable catalog of ECU/PCM tuning files.

Walks files/, merges human-curated metadata.yaml, computes SHA-256 checksums,
and emits a static website (catalog/) with a JSON search index.

Usage:
    python build_catalog.py                    # build from project root
    python build_catalog.py --meta other.yaml  # alternate metadata file

Only dependency: PyYAML   (pip install pyyaml)
"""

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Install it with:  pip install pyyaml")

META_FIELDS = [
    "type", "manufacturer", "ecu", "os_id", "cal_id",
    "vehicle", "engine", "years", "transmission",
    "description", "source", "source_url", "xdf", "tags",
    "verified", "notes",
]

VALID_TYPES = {"stock", "tune", "xdf", "tool", "doc", "other"}


def norm(p):
    return p.replace("\\", "/").strip().strip("/")


def sha256_of(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def load_metadata(path):
    if not path.exists():
        print(f"NOTE: {path.name} not found -- continuing with no metadata.")
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries = {}
    for e in data.get("files", []):
        p = e.get("path")
        if not p:
            print(f"  WARNING: metadata entry missing 'path': {e}")
            continue
        entries[norm(p)] = e
    return entries


def scan_files(files_dir):
    found = {}
    if not files_dir.exists():
        return found
    for p in sorted(files_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(files_dir).as_posix()
        if any(part.startswith(".") for part in rel.split("/")):
            continue  # skip .gitkeep etc.
        found[norm(rel)] = p
    return found


def build_entries(found, metadata, files_url):
    entries, missing, dangling = [], [], []
    for rel, path in sorted(found.items()):
        meta = metadata.get(rel, {})
        st = path.stat()
        e = {
            "path": rel,
            "name": Path(rel).name,
            "size": st.st_size,
            "sha256": sha256_of(path),
            "modified": datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc
            ).isoformat(timespec="seconds"),
            "download_url": files_url.rstrip("/") + "/"
            + "/".join(quote(s) for s in rel.split("/")),
            "needs_metadata": not bool(meta),
        }
        for k in META_FIELDS:
            if k in meta and meta[k] not in (None, ""):
                e[k] = meta[k]
        if e.get("type") and e["type"] not in VALID_TYPES:
            print(f"  WARNING: unknown type '{e['type']}' on {rel}")
        if e.get("xdf") and norm(e["xdf"]) not in found:
            dangling.append((rel, e["xdf"]))
        entries.append(e)
        if not meta:
            missing.append(rel)
    return entries, missing, dangling


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--files-dir", default="files")
    ap.add_argument("--meta", default="metadata.yaml")
    ap.add_argument("--templates", default="templates")
    ap.add_argument("--out", default="catalog")
    ap.add_argument("--files-url", default="/files/")
    a = ap.parse_args()

    root = Path(a.root)
    files_dir = root / a.files_dir
    meta_path = root / a.meta
    tpl_dir = root / a.templates
    out_dir = root / a.out

    files_dir.mkdir(parents=True, exist_ok=True)

    metadata = load_metadata(meta_path)
    found = scan_files(files_dir)
    entries, missing, dangling = build_entries(found, metadata, a.files_url)
    orphans = sorted(set(metadata) - set(found))

    out_dir.mkdir(parents=True, exist_ok=True)

    index = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(entries),
        "files_url": a.files_url,
        "files": entries,
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    with open(out_dir / "sha256sums.txt", "w", encoding="utf-8", newline="\n") as f:
        for e in entries:
            f.write(f'{e["sha256"]}  {e["path"]}\n')

    for name in ("index.html", "app.js", "style.css"):
        src = tpl_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)

    # ---- summary ----
    types = Counter(e.get("type", "unspecified") for e in entries)
    makers = Counter(e.get("manufacturer", "?") for e in entries)
    print(f"Catalog built: {len(entries)} files -> {out_dir}/")
    print("  by type: " + (", ".join(f"{k}={v}" for k, v in sorted(types.items())) or "-"))
    print("  makers:  " + (", ".join(f"{k}={v}" for k, v in sorted(makers.items())) or "-"))
    if missing:
        print(f"\nFiles MISSING metadata ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")
    if orphans:
        print(f"\nMetadata entries with NO matching file ({len(orphans)}):")
        for o in orphans:
            print(f"  - {o}")
    if dangling:
        print("\nDangling XDF references (xdf file not in archive):")
        for src, xdf in dangling:
            print(f"  - {src} -> {xdf}")
    if entries and not missing and not orphans and not dangling:
        print("All metadata checks passed.")


if __name__ == "__main__":
    main()
