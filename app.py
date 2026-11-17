#!/usr/bin/env python3
"""
app.py -- submission server for the Tuning Files Archive (Phase 3).

Runs alongside the static catalog; nginx proxies /submit and /review here.

  GET  /                  small landing page
  GET  /submit            public upload form
  POST /submit            receive file + metadata -> files/_inbox/ (never published)
  GET  /review            maintainer queue (?key=... required when REVIEW_KEY set)
  POST /review/publish    move file into the archive, append metadata, rebuild
  POST /review/reject     delete a submission

Config (env vars, or an app.env file loaded by systemd):
  ARCHIVE_ROOT   project root (default: directory containing this file)
  REVIEW_KEY     secret guarding /review
  PORT           listen port (default 5001, bound to 127.0.0.1)

Dependencies: flask, pyyaml  (pip install -r requirements.txt)
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

APP_DIR = Path(__file__).resolve().parent
ARCHIVE_ROOT = Path(os.environ.get("ARCHIVE_ROOT", APP_DIR))
REVIEW_KEY = os.environ.get("REVIEW_KEY", "")
INBOX = ARCHIVE_ROOT / "files" / "_inbox"
CATALOG_INDEX = ARCHIVE_ROOT / "catalog" / "index.json"
METADATA_YAML = ARCHIVE_ROOT / "metadata.yaml"
MAX_CONTENT_LENGTH = 64 * 1024 * 1024
ALLOWED_EXT = {".bin", ".xdf", ".cal", ".xml"}

app = Flask(__name__, template_folder="app_templates")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-in-production")


def norm(p):
    return p.replace("\\", "/").strip().strip("/")


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_index():
    if CATALOG_INDEX.exists():
        try:
            return json.loads(CATALOG_INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"files": []}


def check_key():
    if REVIEW_KEY and request.values.get("key", "") != REVIEW_KEY:
        abort(403)


def auto_checks(saved_path, form):
    """Automatic half of the metadata: checksum, duplicate scan, embedded IDs."""
    data = saved_path.read_bytes()
    checks = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    for e in load_index().get("files", []):
        if e.get("sha256") == checks["sha256"]:
            checks["duplicate_of"] = e["path"]
            break
    # embedded-ID verification applies to calibration images, not definitions
    if form.get("type") != "xdf" and saved_path.suffix.lower() in (".bin", ".cal"):
        for idk in ("os_id", "cal_id"):
            claimed = (form.get(idk) or "").strip()
            if claimed:
                checks[idk + "_in_bin"] = claimed.encode() in data
    return checks


@app.route("/")
def home():
    return render_template("submit.html")


@app.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "GET":
        return render_template("submit.html")

    form = request.form
    f = request.files.get("file")
    if not f or not f.filename:
        return render_template("submit.html", error="No file selected."), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return render_template(
            "submit.html", error=f"Extension '{ext}' not allowed (bin/xdf/cal/xml)."), 400
    for field in ("type", "manufacturer", "vehicle", "source"):
        if not (form.get(field) or "").strip():
            return render_template("submit.html", error=f"Missing required field: {field}"), 400
    if not (form.get("agreement") or "").strip():
        return render_template(
            "submit.html",
            error="You must confirm the sharing agreement (personal/educational use)."), 400

    INBOX.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved_name = f"{stamp}_{secure_filename(f.filename)}" or f"{stamp}_upload"
    saved_path = INBOX / saved_name
    f.save(saved_path)

    checks = auto_checks(saved_path, form)
    sidecar = {
        "saved_name": saved_name,
        "original_name": f.filename,
        "submitted": utcnow(),
        "form": {k: v for k, v in form.items()},
        "checks": checks,
    }
    (INBOX / (saved_name + ".json")).write_text(
        json.dumps(sidecar, indent=1, ensure_ascii=False), encoding="utf-8")
    return render_template("submit.html", done=True, item=sidecar)


def list_pending():
    items = []
    if not INBOX.exists():
        return items
    for jf in sorted(INBOX.glob("*.json")):
        try:
            item = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        form = item.get("form", {})
        maker = form.get("manufacturer") or "GM"
        ecu = form.get("ecu") or "unknown"
        osid = form.get("os_id") or "unknown"
        kind = "xdf" if form.get("type") == "xdf" else "stock"
        item["suggest_dir"] = f"{maker}/{ecu}/{osid}/{kind}"
        item["suggest_name"] = item.get("original_name", "")
        item["_sidecar"] = jf.name
        item["_file"] = INBOX / item.get("saved_name", "")
        item["_file_exists"] = item["_file"].is_file()
        items.append(item)
    return items


@app.route("/review")
def review():
    check_key()
    return render_template("review.html", items=list_pending(), key=REVIEW_KEY)


def build_entry(item, target_rel, pf):
    form = item["form"]
    tags = [t.strip() for t in (form.get("tags") or "").split(",") if t.strip()]
    checks = item.get("checks", {})
    note_parts = []
    if form.get("contact"):
        note_parts.append(f"submitted by {form['contact']}")
    note_parts.append(f"submitted {item['submitted']} via web form")
    if checks.get("duplicate_of"):
        note_parts.append(f"AUTO-CHECK: byte-identical to {checks['duplicate_of']}")
    for idk in ("os_id", "cal_id"):
        if idk + "_in_bin" in checks:
            state = "found" if checks[idk + "_in_bin"] else "NOT found"
            note_parts.append(f"AUTO-CHECK: {idk} {state} embedded in bin")
    if pf.get("notes"):
        note_parts.append("maintainer: " + pf["notes"])
    entry = {
        "path": target_rel,
        "type": form.get("type", "other"),
        "manufacturer": form.get("manufacturer", ""),
        "ecu": form.get("ecu", ""),
        "module": form.get("module", ""),
        "os_id": form.get("os_id", ""),
        "cal_id": form.get("cal_id", ""),
        "vehicle": pf.get("vehicle", form.get("vehicle", "")),
        "engine": pf.get("engine", form.get("engine", "")),
        "years": pf.get("years", form.get("years", "")),
        "transmission": form.get("transmission", ""),
        "description": pf.get("description", form.get("description", "")),
        "source": form.get("source", ""),
        "source_url": form.get("source_url", ""),
        "tags": tags,
        "verified": False,
    }
    entry = {k: v for k, v in entry.items() if v not in (None, "", [])}
    entry["notes"] = "; ".join(note_parts)
    return entry


def review_url():
    return url_for("review") + (f"?key={REVIEW_KEY}" if REVIEW_KEY else "")


@app.route("/review/publish", methods=["POST"])
def publish():
    check_key()
    saved_name = secure_filename(request.form.get("saved_name", ""))
    sidecar_path = INBOX / (saved_name + ".json")
    if not sidecar_path.exists():
        flash("Submission not found (already published or rejected?).", "error")
        return redirect(review_url())
    item = json.loads(sidecar_path.read_text(encoding="utf-8"))
    src = INBOX / saved_name
    if not src.is_file():
        flash("Submitted file is missing from the inbox.", "error")
        return redirect(review_url())

    target_dir = norm(request.form.get("target_dir", ""))
    target_name = (request.form.get("target_name", "").strip()
                   or item.get("original_name", "unnamed.bin"))
    entry_path = norm(f"{target_dir}/{target_name}")   # relative to files/
    segments = entry_path.split("/")
    if ".." in segments or segments[0].startswith("_") or len(segments) < 2:
        flash("Invalid target path.", "error")
        return redirect(review_url())
    target = ARCHIVE_ROOT / "files" / entry_path
    if target.exists():
        flash(f"Target already exists, not published: {entry_path}", "error")
        return redirect(review_url())

    entry = build_entry(item, entry_path, request.form)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil_move(str(src), str(target))
    sidecar_path.unlink(missing_ok=True)

    dumped = yaml.safe_dump([entry], default_flow_style=False, sort_keys=False,
                            allow_unicode=True, width=1000)
    indented = "\n".join(("  " + ln) if ln.strip() else ln for ln in dumped.splitlines())
    with open(METADATA_YAML, "a", encoding="utf-8") as mf:
        mf.write("\n" + indented + "\n")

    build = subprocess.run([sys.executable, "build_catalog.py"], cwd=ARCHIVE_ROOT,
                           capture_output=True, text=True)
    if build.returncode == 0:
        flash(f"Published {entry_path} and rebuilt the catalog.", "ok")
    else:
        flash(f"Published {entry_path} BUT catalog rebuild failed:", "error")
        flash((build.stdout + build.stderr)[-3000:], "error")
    return redirect(review_url())


@app.route("/review/reject", methods=["POST"])
def reject():
    check_key()
    saved_name = secure_filename(request.form.get("saved_name", ""))
    sidecar = INBOX / (saved_name + ".json")
    f = INBOX / saved_name
    if sidecar.exists():
        sidecar.unlink()
    if f.exists():
        f.unlink()
    flash("Rejected and deleted.")
    return redirect(review_url())


# shutil.move but tolerant of cross-device moves on Windows dev boxes
def shutil_move(src, dst):
    import shutil
    try:
        shutil.move(src, dst)
    except OSError:
        shutil.copy2(src, dst)
        Path(src).unlink()


if __name__ == "__main__":
    INBOX.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5001)))
