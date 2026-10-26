#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copies Tessera builds from the registry into one OCI image layout (each layer stored once).
#   tools/fetch-images.sh DEST [build ...]      builds: tessera tessera-nvidia tessera-nvidia-open (default: all)
set -euo pipefail
DEST=$1; shift || true
REGISTRY=${TESSERA_REGISTRY:-ghcr.io/herbalchemist}
TAG=${TESSERA_TAG:-latest}
builds=("$@"); [ ${#builds[@]} -gt 0 ] || builds=(tessera tessera-nvidia tessera-nvidia-open)
mkdir -p "$DEST"
for b in "${builds[@]}"; do
  echo "== $b"
  skopeo copy --retry-times 3 "docker://$REGISTRY/$b:$TAG" "oci:$DEST:$b"
done
du -sh "$DEST"
