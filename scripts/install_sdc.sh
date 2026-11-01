#!/usr/bin/env bash
# Install or upgrade inside the SDC (NO internet needed).
# Run from inside the unpacked bundle folder:
#
#   sudo ./source/scripts/install_sdc.sh [/opt/aci]
set -euo pipefail

BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET="${1:-/opt/aci}"

echo "==> Verifying bundle checksums"
python3 "$BUNDLE/source/scripts/verify_bundle.py" "$BUNDLE"

echo "==> Loading Docker images"
docker load -i "$BUNDLE/images.tar"

echo "==> Installing files to $TARGET"
mkdir -p "$TARGET"
cp -r "$BUNDLE/source/." "$TARGET/"
mkdir -p "$TARGET/models" "$TARGET/docker/certs" "$TARGET/clamav-db"
cp -r "$BUNDLE/models/." "$TARGET/models/"
cd "$TARGET"

if [ ! -f .env ]; then
  echo "==> Creating .env with random secrets"
  rand() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
  ADMIN_PW="Admin-$(rand 9)"
  sed -e "s|^SECRET_KEY=.*|SECRET_KEY=$(rand 48)|" \
      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand 24)|" \
      -e "s|^BOOTSTRAP_ADMIN_PASSWORD=.*|BOOTSTRAP_ADMIN_PASSWORD=${ADMIN_PW}|" \
      .env.example > .env
  echo "ACI_VERSION=$(cat "$BUNDLE/VERSION")" >> .env
  chmod 600 .env
  echo
  echo "   First admin login:  user 'admin'  password '${ADMIN_PW}'"
  echo "   (you must change it at first login; it is also stored in $TARGET/.env)"
  echo
else
  sed -i "s|^ACI_VERSION=.*|ACI_VERSION=$(cat "$BUNDLE/VERSION")|" .env
fi

if [ ! -f docker/certs/server.crt ]; then
  echo "==> No TLS certificate found: creating a temporary self-signed one"
  openssl req -x509 -newkey rsa:3072 -nodes -days 365 -subj "/CN=$(hostname -f)" \
    -keyout docker/certs/server.key -out docker/certs/server.crt
  chmod 600 docker/certs/server.key
  echo "   Replace docker/certs/server.crt/.key with the department certificate."
fi

PROFILE=""
if ls clamav-db/*.cvd clamav-db/*.cld >/dev/null 2>&1; then PROFILE="--profile clamav"; fi
echo "==> Starting services"
docker compose $PROFILE up -d
docker compose ps
echo "Done. Open https://$(hostname -f)/"
