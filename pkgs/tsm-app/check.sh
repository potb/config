#!/usr/bin/env bash
set -uo pipefail

CONFIG_DIR="${CONFIG_DIR:-/home/potb/projects/potb/config}"
PKG="${CONFIG_DIR}#nixosConfigurations.charon.pkgs.tsm-app"

KEEP_GOING=0
[ "${1:-}" = "--keep-going" ] && KEEP_GOING=1

FAILED=0

stage() {
  local name="$1"
  shift
  local start=$SECONDS
  local out
  out=$("$@" 2>&1)
  local code=$?
  local dur=$((SECONDS - start))

  if [ $code -eq 0 ]; then
    printf 'PASS  %-24s %4ds\n' "$name" "$dur"
    return 0
  fi

  printf 'FAIL  %-24s %4ds  (exit %d)\n' "$name" "$dur" "$code"
  printf '%s\n' "$out" | tail -40 | sed 's/^/      | /'
  FAILED=1
  [ $KEEP_GOING -eq 0 ] && exit 1
  return 0
}

build_path() {
  nix build "$PKG" --no-link --print-out-paths
}

flake_evaluates() {
  nix eval --raw \
    "${CONFIG_DIR}#nixosConfigurations.charon.config.system.build.toplevel.drvPath"
}

derivation_evaluates() {
  nix eval --raw "${PKG}.drvPath"
}

package_builds() {
  build_path
}

binary_present() {
  local out
  out=$(build_path) || return 1
  test -x "$out/bin/tsm-app"
}

imports_headless() {
  local out
  out=$(build_path) || return 1
  QT_QPA_PLATFORM=offscreen "$out/bin/tsm-app" --version
}

stage "flake evaluates"      flake_evaluates
stage "derivation evaluates" derivation_evaluates
stage "package builds"       package_builds
stage "binary present"       binary_present
stage "imports headless"     imports_headless

if [ $FAILED -eq 0 ]; then
  echo "all stages passed"
else
  echo "some stages failed"
  exit 1
fi
