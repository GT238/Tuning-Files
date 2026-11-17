# Tuning Files Archive

A searchable, self-hosted archive of ECU/PCM tuning files: calibration `.bin`
images, `.xdf` definitions, and user tunes. Multi-manufacturer (GM-heavy),
covering both stock/reference calibrations and user-created tunes, for both
PCM (engine) and TCM (transmission) modules.

Built to outlive any single forum: files are checksummed, versioned in git,
and served as a plain static site.

## Quick start

```bash
pip install pyyaml
python build_catalog.py          # generates catalog/ from files/ + metadata.yaml
python -m http.server 8000       # local preview: http://localhost:8000/catalog/
```

## Project layout

```
.
├── build_catalog.py        # generator: scans files/, merges metadata, builds the site
├── metadata.yaml           # human-curated info for every file (the important part)
├── files/                  # THE ARCHIVE -- all bins, xdfs, tunes
│   └── <Manufacturer>/<ECU family>/<OS or Cal ID>/{stock,tunes,xdf,...}/
│       examples:
│       GM/E38/12600587/stock/12600587_OS.bin
│       GM/E38/12600587/tunes/12600587_stage1.bin
│       GM/E38/12600587/xdf/12600587.xdf
│       GM/Car-LS/...   (car LS1/LS2/LS6 modules)
│       GM/Car-V6/...   (pushrod V6 car modules)
│       GM/Duramax-LLY/...
│       GM/TCM/...      (transmission modules)
│       GM/Unverified/...  (odd sizes / unidentified -- do not flash)
├── templates/              # site templates (copied into catalog/ on each build)
├── catalog/                # GENERATED -- do not edit by hand (gitignored)
│   ├── index.html  app.js  style.css
│   ├── index.json          # search index
│   └── sha256sums.txt      # checksums for every archived file
└── deploy/                 # nginx config + deploy script for the Hetzner server
```

The `<ECU family>` segment is free-form. Use what the community uses
(`E38`, `E67`, `Car-LS`, `TCM`, ...). When a file's identity is uncertain,
park it under `Unverified/` rather than guessing -- a wrong ID in the path
is worse than an obvious "we don't know yet".

## Daily workflow

1. Drop files into `files/` following the layout above. Keep stock calibrations
   and user tunes in separate subfolders. Keep original filenames (provenance).
2. Add one entry per file to `metadata.yaml` (see the commented examples there).
   Files without an entry still appear on the site, flagged **needs info** in red.
3. Run `python build_catalog.py`. It prints warnings for: files missing metadata,
   metadata entries with no file, bad `type` values, dangling `xdf` references,
   claimed OS/CAL IDs that are **not embedded in the bin** (a strong sign the
   filename is wrong), and byte-identical duplicate files.
4. Deploy: `bash deploy/deploy.sh` (or rsync manually, see below).

## Metadata schema

| field | required | notes |
|---|---|---|
| `path` | yes | location under `files/`, forward slashes |
| `type` | yes | `stock` \| `tune` \| `xdf` \| `tool` \| `doc` \| `other` |
| `manufacturer` | yes | `GM`, `Ford`, `Chrysler`, ... |
| `ecu` | yes | ECU family, e.g. `E38`, `E67`, `Car-LS`, `EEC-V`, `ME7.6` |
| `module` | recommended | `PCM` \| `ECM` \| `TCM` -- which module the file belongs to |
| `os_id` / `cal_id` | when known | OS/flash ID and calibration ID |
| `module`... | | (see above) |
| `vehicle` / `engine` / `years` | recommended | what the calibration belongs to |
| `description` | recommended | short human notes |
| `source` / `source_url` | recommended | provenance -- where the file came from |
| `author` | optional | who made the file (XDF author, tuner) -- credit where due |
| `aliases` | optional | list of alternative names the file is known by (e.g. former duplicate filenames) -- searchable, shown as "aka" |
| `xdf` | optional | path of a compatible XDF (linked from the site). When exactly one archived XDF exists for the bin's OS ID, the generator auto-links it; multiple candidates are reported for a manual pick |
| `tools` | optional | list of paths of related tools (checksum plugins etc.), linked from the site. For Car-LS/P59 bins without one, the generator auto-suggests the P01/P59 checksum plugin |
| `tags` | optional | free-form keywords |
| `verified` | optional | `true` if checksum confirmed against known-good copy |
| `notes` | optional | anything else |

`duplicate_of` is set automatically by the generator for byte-identical files
(never edit it by hand). The generator also records `os_id_in_bin` /
`cal_id_in_bin` -- whether the claimed IDs actually appear as text inside the
bin -- and flags mismatches. A green **verified** badge on the site means
`verified: true`; everything else should be treated as "trust but verify".

## Trust & verification

- Every file gets a SHA-256 at build time; the site shows a truncated hash with
  a copy button, and `catalog/sha256sums.txt` lists them all.
- Claimed OS/CAL IDs are checked against the bin's actual contents. Filenames
  in the wild are frequently mislabeled (wrong OS number, wrong vehicle) --
  the **ID?** badge marks files where the claimed ID is not embedded.
- TCM bins (and some ECM bins) can contain the **VIN of the donor vehicle**
  embedded in the file. That's normal, but be aware when sharing.

## Deploying to the Hetzner server

No domain needed yet -- the site runs on the server IP or its
`your-server.de` hostname.

```bash
# one-time, on the server (Debian/Ubuntu)
sudo apt update && sudo apt install -y nginx
sudo mkdir -p /srv/tuning-files
sudo cp -r catalog files /srv/tuning-files/
sudo cp deploy/nginx-tuning-files.conf /etc/nginx/sites-available/tuning-files
sudo ln -s /etc/nginx/sites-available/tuning-files /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

- Open TCP port 80 in the **Hetzner Cloud firewall** (console) and in the
  server's local firewall (`sudo ufw allow 80/tcp` if used).
- Browse to `http://<server-ip>/`. To get a stable name, set the server's
  reverse DNS in the Hetzner Robot panel -- you can then browse
  `http://sXXXXX.your-server.de/`.
- Later: point a domain at the IP and add HTTPS with certbot.

**Updating** (from your local machine):

```bash
python build_catalog.py
bash deploy/deploy.sh        # rsyncs catalog/ and files/ to the server
```

`deploy/deploy.sh` honors `SERVER=user@host` and `DEST=/srv/tuning-files`
environment variables. Alternatively, keep the whole project on the server
and build there over SSH.

## Verifying downloads

`catalog/sha256sums.txt` lists a SHA-256 for every archived file (paths are
relative to `files/`):

```bash
cd files && sha256sum -c ../catalog/sha256sums.txt
```

On Windows: `certutil -hashfile somefile.bin SHA256` and compare with the
checksum shown on the site (click "copy" next to any row).

## GM OS vs CAL — why the archive is filed by OS

GM calibrations are two layers: the **OS** (operating system — the firmware base)
and the **CAL** (calibration — the vehicle/engine-specific parameters). In
practice:

- An OS ID is **year/platform-wide, not vehicle-specific**. The same OS (e.g.
  12587603, "7603") ships in cars *and* trucks; one OS serves many vehicles.
- What distinguishes a Silverado from a Corvette on the same OS is the **CAL ID**.
- So "same OS, different bytes" between two bins is *normal* — it means two
  applications, not a mislabeled file.

The archive's folder taxonomy (`<ecu>/<os-id>/...`) mirrors this: bins group by
OS, and the metadata's `cal_id` field carries the application-specific part.
When adding bins, always record the CAL ID if you can get it (EFILive/TunerPro
show it; for many bins it's also embedded as text — the generator verifies the
OS ID this way). A bin without a CAL ID is only half-identified.

## XDF definitions

Definitions live alongside the bins they apply to (`files/<...>/xdf/`) and appear in the **same catalog** with an XDF badge — one search results page, not a separate section. Bins link to their definition (⧉ XDF chip); definition rows show "used by" links back to the bins they apply to. Search an OS ID (e.g. `12592618`) to see the calibrations and their definition together.

The generator does **not** run the embedded-ID check on XDFs — they are definitions, not calibration images, so their OS attribution comes from the filename.

## Submissions & uploads

**Phase 1 (now): maintainer-curated.** You collect files, write metadata, rebuild. This is what keeps the archive trustworthy.

**Phase 2 (implemented): submission drop zone.** `files/_inbox/` is a drop zone on the server. The catalog generator skips any folder starting with `_`, so dropped files are invisible until published. Submitters include a note (vehicle, engine, source); the maintainer verifies (checksum, duplicate check, embedded-ID check — all automatic), writes the metadata entry, moves the file into the tree, and rebuilds.

**Phase 3 (implemented): web upload form.** A small Flask app (`app.py`) runs
alongside the static catalog; nginx proxies `/submit` and `/review` to it (see
`deploy/nginx-tuning-files.conf`).

- `/submit` — public form: file + metadata fields + "I have the right to share
  this / personal use only" checkbox. On submit, the file lands in
  `files/_inbox/` (never published, blocked in nginx) together with a `.json`
  sidecar holding the form data and the automatic checks: SHA-256, duplicate
  detection against the published catalog, and embedded OS/CAL ID verification.
- `/review?key=...` — maintainer queue (guarded by `REVIEW_KEY`): shows pending
  submissions with their auto-check badges, and lets you **publish** (pick the
  target folder + filename → file is moved, the entry is appended to
  `metadata.yaml`, and the catalog rebuilds) or **reject** (deleted).

Running on the server:

```bash
cd /srv/tuning-files
python3 -m pip install -r requirements.txt
# app.env:  REVIEW_KEY=<pick a secret>   (ARCHIVE_ROOT defaults to the app's directory)
sudo cp deploy/tuning-files-upload.service /etc/systemd/system/
sudo systemctl enable --now tuning-files-upload
```

The Flask app binds to 127.0.0.1:5001; only `/submit` and `/review` are exposed
through nginx. `deploy/deploy.sh` syncs `app.py` + `app_templates/` too,
restarts the service, and deliberately **excludes `files/_inbox/`** from rsync
so pending submissions on the server are never wiped by a deploy.

What's automatic vs human for every file:
- **Automatic:** SHA-256, size, byte-identical duplicate detection, claimed OS/CAL ID vs bin content (catches mislabeled filenames), XDF↔bin ID matching.
- **From submitter:** vehicle, engine, years, transmission, description, source.
- **From maintainer review:** ECU family attribution, `verified` flag, notes.

## Notes / roadmap ideas

- Git handles this scale fine; if the archive grows to tens of GB, move
  `files/` to git-lfs or keep it only on the server and track just
  `metadata.yaml` in git.
- Community contributions later: an upload endpoint or a submission queue
  (files land in an inbox, maintainer adds metadata, rebuild).
- Per-file sidecar metadata (`foo.bin.meta.json`) instead of one big
  `metadata.yaml`, once many people edit it.

## Legal note

Calibration files are proprietary data owned by the OEMs. This archive
operates on the community norm of personal/educational use. The site footer
carries a disclaimer; takedown/ownership requests are routed through GitHub
issues (the Issues tab of this repo) and are honored promptly. Don't upload
files you don't have the right to share, and keep provenance (`source`) in
the metadata so trust is earned, not assumed.
