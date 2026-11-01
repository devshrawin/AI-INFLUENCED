#!/usr/bin/env bash
# Build everything needed for the State Data Centre into ONE .tar file.
# Run on an INTERNET-connected Linux machine with Docker, from the repo root:
#
#   ./scripts/package_offline.sh [--gpu] [--no-clamav] [--skip-models-download] [--models-dir DIR]
#
# Output: dist/aci-offline-<version>.tar  containing
#   images.tar          Docker images (app, postgres, nginx, [clamav])
#   models/             model weights + MANIFEST.json (checksums)
#   wheels/             Python wheels (to rebuild the app image offline if needed)
#   source/             this repository (compose files, scripts, docs)
#   SHA256SUMS          checksums of every file above
set -euo pipefail

GPU=0; CLAMAV=1; DOWNLOAD=1; MODELS=models
while [ $# -gt 0 ]; do
  case "$1" in
    --gpu) GPU=1 ;;
    --no-clamav) CLAMAV=0 ;;
    --skip-models-download) DOWNLOAD=0 ;;
    --models-dir) MODELS="$2"; shift ;;
    *) echo "Unknown option $1"; exit 2 ;;
  esac
  shift
done

cd "$(dirname "$0")/.."
VERSION="$(git describe --tags --always --dirty 2>/dev/null || date +%Y%m%d)"
OUT="dist/aci-offline-${VERSION}"
rm -rf "$OUT"; mkdir -p "$OUT"/{models,wheels,source}

echo "==> 1/6 Downloading models"
if [ "$DOWNLOAD" = 1 ]; then
  python3 scripts/download_models.py --dest "$MODELS"
fi
test -f "$MODELS/MANIFEST.json" || { echo "$MODELS/MANIFEST.json missing"; exit 1; }

echo "==> 2/6 Building app image (aci-app:${VERSION})"
TORCH_INDEX="https://download.pytorch.org/whl/cpu"
[ "$GPU" = 1 ] && TORCH_INDEX="https://download.pytorch.org/whl/cu126"
# Behind a TLS-inspecting proxy: export PIP_CA_BUNDLE=/path/to/proxy-ca.pem
SECRET_ARGS=()
[ -n "${PIP_CA_BUNDLE:-}" ] && SECRET_ARGS=(--secret "id=ca_bundle,src=${PIP_CA_BUNDLE}")
docker build -f docker/Dockerfile --build-arg TORCH_INDEX_URL="$TORCH_INDEX" "${SECRET_ARGS[@]}" \
  -t "aci-app:${VERSION}" -t aci-app:latest .

echo "==> 3/6 Pulling and saving images"
IMAGES=("aci-app:${VERSION}" "aci-app:latest" "postgres:16-alpine" "nginx:1.27-alpine")
[ "$CLAMAV" = 1 ] && IMAGES+=("clamav/clamav:1.4")
for img in "${IMAGES[@]:2}"; do
  # Use the local copy if the registry is unreachable or rate-limited.
  docker pull "$img" || docker image inspect "$img" >/dev/null || { echo "Cannot get $img"; exit 1; }
done
docker save -o "$OUT/images.tar" "${IMAGES[@]}"

echo "==> 4/6 Downloading Python wheels"
python3 -m pip download -d "$OUT/wheels" -r requirements.txt -c <(grep -v '^torch==' requirements.lock) \
  --python-version 3.11 --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 --only-binary=:all:
TORCH_VERSION=$(grep -i '^torch==' requirements.lock | cut -d= -f3 | cut -d+ -f1)
python3 -m pip download -d "$OUT/wheels" "torch==${TORCH_VERSION}" --index-url "$TORCH_INDEX" \
  --python-version 3.11 --platform manylinux_2_28_x86_64 --only-binary=:all: --no-deps

echo "==> 5/6 Copying models and source"
cp -r "$MODELS/." "$OUT/models/"
rm -rf "$OUT"/models/*/.cache
git archive --format=tar HEAD | tar -x -C "$OUT/source"
echo "$VERSION" > "$OUT/VERSION"

echo "==> 6/6 Writing checksums and bundle"
( cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
tar -cf "dist/aci-offline-${VERSION}.tar" -C dist "aci-offline-${VERSION}"
( cd dist && sha256sum "aci-offline-${VERSION}.tar" > "aci-offline-${VERSION}.tar.sha256" )
echo
echo "Bundle: dist/aci-offline-${VERSION}.tar"
echo "Checksum: $(cat "dist/aci-offline-${VERSION}.tar.sha256")"
echo "Copy BOTH files to the SDC and follow docs/SDC_DEPLOYMENT.md"
