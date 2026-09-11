#!/usr/bin/env bash
set -euo pipefail

root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
out="$root/checks/openclaw-config-schema.json.gz"

schema=$(nix build --no-link --print-out-paths \
  "$root#nixosConfigurations.new-horizons.config.services.openclaw-gateway.package" \
  2>/dev/null)

mkdir -p "$root/checks"

HOME=$(mktemp -d) "$schema/bin/openclaw" config schema |
  python3 -c '
import gzip, json, sys
data = json.load(sys.stdin)
body = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
with gzip.GzipFile(sys.argv[1], "wb", compresslevel=9, mtime=0) as handle:
    handle.write(body)
' "$out"

echo "wrote $out"
