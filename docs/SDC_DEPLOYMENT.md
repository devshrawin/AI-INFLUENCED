# Installing the Upload Integrity Check in the State Data Centre

This guide is for the SDC IT team. Follow the steps in order. No internet
connection is needed inside the SDC.

---

## 1. What you need

### Server (one virtual machine)

| | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores (x86-64) | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB free | 50 GB (database grows ~1 KB per uploaded file) |
| GPU | not needed | not needed |
| OS | Linux x86-64 (RHEL 9, Ubuntu 22.04/24.04, Debian 12) | |

The app itself uses about 200 MB of RAM. One check takes about 0.1–0.6 seconds.
A 4-core server handles several thousand uploads per hour.

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
./scripts/package_offline.sh
```

The script prints two files to copy:

```
dist/aci-offline-<version>.tar          (about 1 GB)
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
4. create `/opt/aci/.env` with random passwords, **print the first admin password**
   and the **API key for the scheme platform**. Write them down.
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

### Connect the scheme platform

Give the platform team the server address and the API key (`API_KEYS` in
`/opt/aci/.env`) and point them to `docs/API.md`. Several keys can be listed,
separated by commas: one per platform or environment. Remove a key to revoke it.

---

## 5. Settings (`/opt/aci/.env`)

Change a value, then run `sudo docker compose up -d` to apply it.

| Setting | Default | Meaning |
|---|---|---|
| `API_KEYS` | random | keys the scheme platform uses (comma-separated) |
| `API_RATE_LIMIT` | 600/minute | API calls per key per minute |
| `SAME_PHOTO_MAX_DISTANCE` / `SIMILAR_PHOTO_MAX_DISTANCE` | 10 / 16 | how close two photos must be to count as "same" (high) or "very similar" (review); lower = stricter |
| `MAX_UPLOAD_MB` | 25 | largest file accepted (also change `client_max_body_size` in `docker/nginx.conf`) |
| `STORE_UPLOADS` | false | keep a copy of uploaded files? |
| `RETENTION_HOURS` | 24 | stored uploads are deleted after this time |
| `CLAMAV_REQUIRED` | false | if true, refuse uploads when the virus scanner is down |
| `RATE_LIMIT` | 30/minute | manual checks per officer per minute |
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

## 7. Daily operation

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

## 8. Troubleshooting

| Problem | What to do |
|---|---|
| Page does not open | `docker compose ps`. Check the firewall allows 443. Check `docker compose logs nginx`. |
| Platform gets 401 | Wrong API key. Compare with `API_KEYS` in `.env`; restart after changing it. |
| Platform gets 429 | More calls than `API_RATE_LIMIT`. Raise it in `.env`. |
| "Too many requests" | A user exceeded `RATE_LIMIT`. Wait one minute or raise the limit. |
| Account locked | 5 wrong passwords lock the account for 15 minutes. An admin can **Enable** it on the Users page. |
| "Virus scanner is unavailable" | ClamAV is not running or has no signatures (section 6). |
| Uploads of large files fail | Raise `MAX_UPLOAD_MB` **and** `client_max_body_size` in `docker/nginx.conf`. |

---

## 9. Security notes for the SDC

* The app and database run on an internal Docker network with **no internet route**.
  Only Nginx (ports 80/443) is exposed.
* Do not expose port 8000 or 5432 outside the server.
* Uploaded files are **not stored** by default. The audit log keeps the file's
  SHA-256 fingerprint, the flags and the user, never the content. Photo
  fingerprints (16-character hashes) are kept to find duplicates.
* Keep the API key secret; it allows anyone to submit files and see which
  applications share a photo.
* Restrict SSH access to the server. `.env` contains secrets (it is created
  with permission 600).
