#!/usr/bin/env bash
# Build everything needed for the State Data Centre into ONE .tar file.
# Run on an INTERNET-connected Linux machine with Docker, from the repo root:
#
#   ./scripts/package_offline.sh [--no-clamav]
#
# Output: dist/aci-offline-<version>.tar  containing
#   images.tar          Docker images (app, postgres, nginx, [clamav])
#   wheels/             Python wheels (to rebuild the app image offline if needed)
#   source/             this repository (compose files, scripts, docs)
#   SHA256SUMS          checksums of every file above
set -euo pipefail

CLAMAV=1
for arg in "$@"; do
  case "$arg" in
    --no-clamav) CLAMAV=0 ;;
    *) echo "Unknown option $arg"; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
VERSION="$(git describe --tags --always --dirty 2>/dev/null || date +%Y%m%d)"
OUT="dist/aci-offline-${VERSION}"
rm -rf "$OUT"; mkdir -p "$OUT"/{wheels,source}

echo "==> 1/4 Building app image (aci-app:${VERSION})"
# Behind a TLS-inspecting proxy: export PIP_CA_BUNDLE=/path/to/proxy-ca.pem
SECRET_ARGS=()
[ -n "${PIP_CA_BUNDLE:-}" ] && SECRET_ARGS=(--secret "id=ca_bundle,src=${PIP_CA_BUNDLE}")
docker build -f docker/Dockerfile "${SECRET_ARGS[@]}" \
  -t "aci-app:${VERSION}" -t aci-app:latest .

echo "==> 2/4 Pulling and saving images"
IMAGES=("aci-app:${VERSION}" "aci-app:latest" "postgres:16-alpine" "nginx:1.27-alpine")
[ "$CLAMAV" = 1 ] && IMAGES+=("clamav/clamav:1.4")
for img in "${IMAGES[@]:2}"; do
  # Use the local copy if the registry is unreachable or rate-limited.
  docker pull "$img" || docker image inspect "$img" >/dev/null || { echo "Cannot get $img"; exit 1; }
done
docker save -o "$OUT/images.tar" "${IMAGES[@]}"

echo "==> 3/4 Downloading Python wheels"
python3 -m pip download -d "$OUT/wheels" -r requirements.txt -c requirements.lock \
  --python-version 3.11 --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 --only-binary=:all:

echo "==> 4/4 Copying source and writing checksums"
git archive --format=tar HEAD | tar -x -C "$OUT/source"
echo "$VERSION" > "$OUT/VERSION"

( cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
tar -cf "dist/aci-offline-${VERSION}.tar" -C dist "aci-offline-${VERSION}"
( cd dist && sha256sum "aci-offline-${VERSION}.tar" > "aci-offline-${VERSION}.tar.sha256" )
echo
echo "Bundle: dist/aci-offline-${VERSION}.tar"
echo "Checksum: $(cat "dist/aci-offline-${VERSION}.tar.sha256")"
echo "Copy BOTH files to the SDC and follow docs/SDC_DEPLOYMENT.md"
