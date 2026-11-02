# Tuning Files Archive

A searchable, self-hosted archive of ECU/PCM tuning files: calibration `.bin`
images, `.xdf` definitions, and user tunes. Multi-manufacturer (GM-heavy),
covering both stock/reference calibrations and user-created tunes.

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
│       GM/E38/12600587/xdf/12600587.xdf
│       GM/E38/12600587/tunes/12600587_60hp_stage1.bin
│       Ford/EECV/.../stock/...
├── templates/              # site templates (copied into catalog/ on each build)
├── catalog/                # GENERATED -- do not edit by hand (gitignored)
│   ├── index.html  app.js  style.css
│   ├── index.json          # search index
│   └── sha256sums.txt      # checksums for every archived file
└── deploy/                 # nginx config + deploy script for the Hetzner server
```

## Daily workflow

1. Drop files into `files/` following the layout above. Keep stock calibrations
   and user tunes in separate subfolders. Name bins with their OS/cal ID when known.
2. Add one entry per file to `metadata.yaml` (see the commented examples there).
   Files without an entry still appear on the site, flagged **needs info** in red.
3. Run `python build_catalog.py`. It prints warnings for: files missing metadata,
   metadata entries with no file, bad `type` values, and `xdf` references pointing
   at files not in the archive.
4. Deploy: `bash deploy/deploy.sh` (or rsync manually, see below).

## Metadata schema

| field | required | notes |
|---|---|---|
| `path` | yes | location under `files/`, forward slashes |
| `type` | yes | `stock` \| `tune` \| `xdf` \| `tool` \| `doc` \| `other` |
| `manufacturer` | yes | `GM`, `Ford`, `Chrysler`, ... |
| `ecu` | yes | ECU family, e.g. `E38`, `E67`, `EEC-V`, `ME7.6` |
| `os_id` / `cal_id` | when known | OS/flash ID and calibration ID |
| `vehicle` / `engine` / `years` | recommended | what the calibration belongs to |
| `description` | recommended | short human notes |
| `source` / `source_url` | recommended | provenance -- where the file came from |
| `xdf` | optional | path of a compatible XDF (linked from the site) |
| `tags` | optional | free-form keywords |
| `verified` | optional | `true` if checksum confirmed against known-good copy |
| `notes` | optional | anything else |

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
carries a disclaimer and a takedown contact; honor takedown requests promptly.
Don't upload files you don't have the right to share, and keep provenance
(`source`) in the metadata so trust is earned, not assumed.
