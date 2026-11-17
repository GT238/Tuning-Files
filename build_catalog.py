#!/usr/bin/env python3
"""
build_catalog.py -- generate a static, searchable catalog of ECU/PCM tuning files.

Walks files/, merges human-curated metadata.yaml, computes SHA-256 checksums,
verifies claimed OS/CAL IDs against the bin contents, detects byte-identical
duplicates, and emits a static website (catalog/) with a JSON search index.

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
    "type", "manufacturer", "ecu", "module", "os_id", "cal_id",
    "vehicle", "engine", "years", "transmission",
    "description", "source", "source_url", "author", "aliases", "xdf", "tools", "tags",
    "verified", "notes", "duplicate_of",
]

VALID_TYPES = {"stock", "tune", "xdf", "tool", "doc", "other"}

# checksum plugin auto-suggest: applies to the P01/P59 bin family only
PLUGIN_PATH = "GM/P59/tools/GM-P01-P59-checksum-plugin.dll"
AUTO_TOOL_ECUS = {"Car-LS", "P59"}


def norm(p):
    return p.replace("\\", "/").strip().strip("/")


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
        if any(part.startswith(".") or part.startswith("_") for part in rel.split("/")):
            continue  # skip .gitkeep, _inbox/ (submission drop zone) etc.
        found[norm(rel)] = p
    return found


def build_entries(found, metadata, files_url):
    entries, missing, dangling, id_mismatch = [], [], [], []
    for rel, path in sorted(found.items()):
        meta = metadata.get(rel, {})
        st = path.stat()
        data = path.read_bytes()
        e = {
            "path": rel,
            "name": Path(rel).name,
            "size": st.st_size,
            "sha256": hashlib.sha256(data).hexdigest(),
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
        # auto-suggest the P01/P59 checksum plugin for calibration bins of the
        # family it covers (per the DLL's own strings: "GM P01/P59", 512kB/1MB).
        # Only Car-LS / P59 -- NOT E38/Duramax/TCM/512K-PCM, different families.
        if (not e.get("tools") and e.get("type") in ("stock", "tune")
                and e.get("ecu") in AUTO_TOOL_ECUS and PLUGIN_PATH in found):
            e["tools"] = [PLUGIN_PATH]
            e["tools_suggested"] = True
        if e.get("type") and e["type"] not in VALID_TYPES:
            print(f"  WARNING: unknown type '{e['type']}' on {rel}")
        # verify claimed IDs against bin content (calibration images only --
        # XDFs are XML definitions; their OS attribution comes from the filename)
        for idk in ("os_id", "cal_id"):
            claimed = e.get(idk)
            if claimed and e.get("type") not in ("xdf", "doc", "tool"):
                embedded = str(claimed).encode() in data
                e[idk + "_in_bin"] = embedded
                if not embedded:
                    id_mismatch.append((rel, idk, claimed))
        if e.get("xdf") and norm(e["xdf"]) not in found:
            dangling.append((rel, e["xdf"]))
        for t in (e.get("tools") or []):
            if norm(t) not in found:
                dangling.append((rel, t))
        entries.append(e)
        if not meta:
            missing.append(rel)
    return entries, missing, dangling, id_mismatch


def find_duplicates(entries):
    """Flag byte-identical files; first non-'(1)' name becomes canonical."""
    by_hash = {}
    for e in entries:
        by_hash.setdefault(e["sha256"], []).append(e)
    groups = []
    for group in by_hash.values():
        if len(group) > 1:
            group.sort(key=lambda e: ("(1)" in e["name"], e["path"]))
            canonical = group[0]
            for e in group[1:]:
                e["duplicate_of"] = canonical["path"]
            groups.append([e["path"] for e in group])
    return groups


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--files-dir", default="files")
    ap.add_argument("--meta", default="metadata.yaml")
    ap.add_argument("--templates", default="templates")
    ap.add_argument("--out", default="catalog")
    ap.add_argument("--files-url", default="/files/")
    ap.add_argument("--base-url", default="",
                    help="site base path when served from a subdirectory (e.g. GitHub Pages /Tuning-Files)")
    ap.add_argument("--submit-url", default="/submit",
                    help="where the Submit button points (e.g. GitHub issues when no Flask app is deployed)")
    a = ap.parse_args()

    root = Path(a.root)
    files_dir = root / a.files_dir
    meta_path = root / a.meta
    tpl_dir = root / a.templates
    out_dir = root / a.out

    files_dir.mkdir(parents=True, exist_ok=True)

    metadata = load_metadata(meta_path)
    found = scan_files(files_dir)
    base = a.base_url.rstrip("/")
    files_url_full = base + a.files_url
    entries, missing, dangling, id_mismatch = build_entries(found, metadata, files_url_full)
    dup_groups = find_duplicates(entries)
    orphans = sorted(set(metadata) - set(found))

    out_dir.mkdir(parents=True, exist_ok=True)

    index = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(entries),
        "files_url": files_url_full,
        "submit_url": a.submit_url,
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
    total_mb = sum(e["size"] for e in entries) / (1024 * 1024)
    print(f"Catalog built: {len(entries)} files ({total_mb:.1f} MB) -> {out_dir}/")
    print("  by type: " + (", ".join(f"{k}={v}" for k, v in sorted(types.items())) or "-"))
    print("  makers:  " + (", ".join(f"{k}={v}" for k, v in sorted(makers.items())) or "-"))
    if dup_groups:
        print(f"\nByte-identical duplicate groups ({len(dup_groups)}):")
        for g in dup_groups:
            print(f"  canonical: {g[0]}")
            for d in g[1:]:
                print(f"    duplicate: {d}")
    if missing:
        print(f"\nFiles MISSING metadata ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")
    if id_mismatch:
        print(f"\nClaimed IDs NOT found embedded in bin ({len(id_mismatch)}):")
        for rel, idk, val in id_mismatch:
            print(f"  - {rel}: {idk}={val}")
    if orphans:
        print(f"\nMetadata entries with NO matching file ({len(orphans)}):")
        for o in orphans:
            print(f"  - {o}")
    if dangling:
        print("\nDangling XDF/tools references (target not in archive):")
        for src_, tgt in dangling:
            print(f"  - {src_} -> {tgt}")
    if entries and not missing and not orphans and not dangling and not id_mismatch:
        print("All metadata checks passed.")


if __name__ == "__main__":
    main()
