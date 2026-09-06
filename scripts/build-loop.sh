#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

fingerprint() {
  find . -path ./.git -prune -o -type f -newermt '@0' -printf '%p %T@\n' 2>/dev/null | sort | sha256sum
}

build() {
  clear
  printf '=== %s: building ===\n' "$(date +%T)"
  if nh os build --max-jobs=4; then
    printf '=== %s: OK ===\n' "$(date +%T)"
  else
    printf '=== %s: FAILED ===\n' "$(date +%T)"
  fi
}

last=$(fingerprint)
build
while true; do
  sleep 2
  now=$(fingerprint)
  if [[ "$now" != "$last" ]]; then
    last=$now
    build
  fi
done
