#!/usr/bin/env bash
set -euo pipefail

root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
out="$root/checks/openclaw-config-schema.json.gz"

flake_attr() {
  printf '%s#%s' "$root" "$1"
}

schema=$(nix build --no-link --print-out-paths \
  "$(flake_attr nixosConfigurations.new-horizons.config.services.openclaw-gateway.package)")

python=$(nix build --no-link --print-out-paths \
  "$(flake_attr nixosConfigurations.new-horizons.pkgs.python3)")

pack=$(cat <<'PY'
import gzip, json, sys
data = json.load(sys.stdin)
body = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
with gzip.GzipFile(sys.argv[1], "wb", compresslevel=9, mtime=0) as handle:
    handle.write(body)
PY
)

mkdir -p "$root/checks"

HOME=$(mktemp -d) "$schema/bin/openclaw" config schema |
  "$python/bin/python3" -c "$pack" "$out"

echo "wrote $out"
