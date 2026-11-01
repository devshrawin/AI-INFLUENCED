# Installing the AI Content Indicator in the State Data Centre

This guide is for the SDC IT team. Follow the steps in order. No internet
connection is needed inside the SDC.

---

## 1. What you need

### Server (one virtual machine or physical server)

| | Minimum (CPU only) | Recommended | With GPU (optional) |
|---|---|---|---|
| CPU | 8 cores (x86-64, AVX2) | 16 cores | 8 cores |
| RAM | 16 GB | 32 GB | 16 GB + GPU |
| GPU | – | – | NVIDIA with 16 GB+ memory (e.g. T4, L4, A10) |
| Disk | 60 GB free | 120 GB (SSD) | 60 GB |
| OS | Linux x86-64 (RHEL 9, Ubuntu 22.04/24.04, Debian 12) | | + NVIDIA driver and NVIDIA Container Toolkit |

Why so much memory: the four AI models together use about **9 GB of RAM**.
To use less (8 GB server), set `ENABLE_BINOCULARS=false` in `.env`. Text
accuracy will drop (see LIMITATIONS.md).

**Expected speed on CPU** (8 cores): an image takes about 1 second. A page of
text (400 words) takes about 4 seconds. A 20-page report takes about 1 minute.
A GPU is roughly 10× faster.

### Software on the server
* Docker Engine 24 or newer, with the Docker Compose plugin (`docker compose version`)
* Python 3 (any version 3.8+, only for the checksum script)
* `openssl` (to create a temporary certificate)

### From the department
* A DNS name for the tool, e.g. `aicheck.dept.state.gov.in`
* A TLS certificate and key for that name (`.crt` and `.key`, PEM format)
* Firewall: allow users to reach the server on **TCP 443** (and 80, which redirects to 443)

---

## 2. Prepare the bundle (on a machine WITH internet, outside the SDC)

This is usually done by the vendor or development team.

```bash
git clone <repository> aci && cd aci
./scripts/package_offline.sh            # add --gpu for a GPU server
```

The script prints two files to copy:

```
dist/aci-offline-<version>.tar          (about 15 GB)
dist/aci-offline-<version>.tar.sha256
```

Copy both into the SDC using the approved transfer method (approved media or
data diode).

---

## 3. Check the bundle (inside the SDC)

```bash
sha256sum -c aci-offline-<version>.tar.sha256     # must print: OK
tar -xf aci-offline-<version>.tar
cd aci-offline-<version>
python3 source/scripts/verify_bundle.py .
```

The last command must end with **"All checksums match."** If it says
**VERIFICATION FAILED**, stop and get a fresh copy of the bundle.

---

## 4. Install

```bash
sudo ./source/scripts/install_sdc.sh /opt/aci
```

This will:
1. check the checksums again
2. load the Docker images
3. copy the files to `/opt/aci`
4. create `/opt/aci/.env` with random passwords and **print the first admin password**. Write it down.
5. create a temporary self-signed certificate if none is present
6. start the services

### Put in the real certificate

```bash
sudo cp your-cert.crt /opt/aci/docker/certs/server.crt
sudo cp your-key.key  /opt/aci/docker/certs/server.key
sudo chmod 600 /opt/aci/docker/certs/server.key
cd /opt/aci && sudo docker compose restart nginx
```

### First login

Open `https://<server-name>/` and log in as `admin` with the printed
password. You must choose a new password immediately. Then go to **Users**
and create accounts for officers. Each officer must change their temporary
password at first login.

---

## 5. Settings (`/opt/aci/.env`)

Change a value, then run `sudo docker compose up -d` to apply it.

| Setting | Default | Meaning |
|---|---|---|
| `THRESHOLD_AI` / `THRESHOLD_HUMAN` | 70 / 30 | score limits for "Likely AI" / "Likely Human" |
| `MAX_UPLOAD_MB` | 25 | largest file accepted (also change `client_max_body_size` in `docker/nginx.conf`) |
| `STORE_UPLOADS` | false | keep a copy of uploaded files? |
| `RETENTION_HOURS` | 24 | stored uploads are deleted after this time |
| `CLAMAV_REQUIRED` | false | if true, refuse uploads when the virus scanner is down |
| `ENABLE_BINOCULARS` | true | the large text model; turn off on small servers |
| `DEVICE` | auto | `auto`, `cpu` or `cuda` |
| `RATE_LIMIT` | 20/minute | checks per user per minute |
| `AUTH_PROVIDER` | local | `local` passwords, or `ldap` (needs development work, see `app/auth/providers.py`) |
| `SECRET_KEY`, `POSTGRES_PASSWORD` | random | **never share; never change `POSTGRES_PASSWORD` after first start** |

---

## 6. Virus scanning with ClamAV (recommended)

ClamAV needs virus signature files. The SDC has no internet, so copy them in.

1. On an internet machine, download `main.cvd`, `daily.cvd` and `bytecode.cvd`
   (for example with the `cvdupdate` tool: `pip install cvdupdate && cvd update`).
2. Copy them into `/opt/aci/clamav-db/` on the server.
3. Start with ClamAV:
   ```bash
   cd /opt/aci && sudo docker compose --profile clamav up -d
   ```
4. Repeat steps 1–2 **every week** to keep signatures current, then run
   `sudo docker compose --profile clamav restart clamav`.

The result screen shows "Virus scan: clean" when ClamAV is working.

---

## 7. GPU servers

1. Build the bundle with `--gpu` (step 2).
2. Install the NVIDIA driver and NVIDIA Container Toolkit on the server
   (offline installers from NVIDIA).
3. Start with:
   ```bash
   sudo docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
   ```

---

## 8. Daily operation

| Task | Command (run in `/opt/aci`) |
|---|---|
| Status | `sudo docker compose ps` (all should be "Up"/"healthy") |
| Logs | `sudo docker compose logs --tail 100 app` |
| Restart | `sudo docker compose restart` |
| Stop / start | `sudo docker compose down` / `sudo docker compose up -d` |
| Reset a password | `sudo docker compose exec app python -m app.cli reset-password <user>` |
| List users | `sudo docker compose exec app python -m app.cli list-users` |

### Backup (daily, recommended)

The database holds users and the audit log.

```bash
sudo docker compose exec -T db pg_dump -U aci aci | gzip > /backup/aci-$(date +%F).sql.gz
```

Restore:
```bash
gunzip -c /backup/aci-YYYY-MM-DD.sql.gz | sudo docker compose exec -T db psql -U aci aci
```

Also back up `/opt/aci/.env` and `/opt/aci/docker/certs/` in a safe place.

### Upgrade to a new version

1. Back up (above).
2. Copy, check and unpack the new bundle (steps 2–3).
3. Run `sudo ./source/scripts/install_sdc.sh /opt/aci` from the new bundle.
   Your `.env`, certificate and database are kept.

---

## 9. Troubleshooting

| Problem | What to do |
|---|---|
| Page does not open | `docker compose ps`. Check the firewall allows 443. Check `docker compose logs nginx`. |
| "Model files not found" warning on results | `/opt/aci/models` is missing files. Re-run `python3 scripts/verify_bundle.py --models-only /opt/aci/models`. |
| App restarts / "Killed" in logs | Not enough RAM. Add RAM or set `ENABLE_BINOCULARS=false`. |
| "Too many requests" | A user exceeded `RATE_LIMIT`. Wait one minute or raise the limit. |
| Account locked | 5 wrong passwords lock the account for 15 minutes. An admin can **Enable** it on the Users page. |
| "Virus scanner is unavailable" | ClamAV is not running or has no signatures (section 6). |
| Uploads of large files fail | Raise `MAX_UPLOAD_MB` **and** `client_max_body_size` in `docker/nginx.conf`. |

---

## 10. Security notes for the SDC

* The app and database run on an internal Docker network with **no internet route**.
  Only Nginx (ports 80/443) is exposed.
* Do not expose port 8000 or 5432 outside the server.
* Uploaded files are **not stored** by default. The audit log keeps the file's
  SHA-256 fingerprint, the scores and the user, but never the content.
* Restrict SSH access to the server. `.env` contains secrets (it is created
  with permission 600).
