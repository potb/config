#!/usr/bin/env bash
set -uo pipefail

CONFIG_DIR="${CONFIG_DIR:-/home/potb/projects/potb/config}"
PKG="${CONFIG_DIR}#nixosConfigurations.charon.pkgs.tsm-app"

KEEP_GOING=0
[ "${1:-}" = "--keep-going" ] && KEEP_GOING=1

FAILED=0

LOG_DIR=$(mktemp -d)
trap 'rm -rf "$LOG_DIR"' EXIT

stage() {
  local name="$1"
  shift
  local start=$SECONDS
  local log="$LOG_DIR/${name// /_}.log"

  printf 'RUN   %-24s ' "$name"
  "$@" > "$log" 2>&1
  local code=$?
  local dur=$((SECONDS - start))

  if [ $code -eq 0 ]; then
    printf '\rPASS  %-24s %4ds\n' "$name" "$dur"
    return 0
  fi

  printf '\rFAIL  %-24s %4ds  (exit %d)\n' "$name" "$dur" "$code"
  tail -40 "$log" | sed 's/^/      | /'
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

run_in_app_env() {
  local out="$1" script="$2" wrapped py sitepaths
  wrapped="$out/bin/.tsm-app-wrapped"
  py=$(sed -n '1s|^#!||p' "$wrapped")
  sitepaths=$(tr "'" '\n' < "$wrapped" | grep '/site-packages$' | paste -sd:)
  QT_QPA_PLATFORM=offscreen PYTHONPATH="$sitepaths" "$py" "$script"
}

local_wow_usable() {
  local out result
  out=$(build_path) || return 1
  run_in_app_env "$out" "$(dirname "$0")/detect_local_wow.py"
  result=$?
  [ $result -eq 77 ] && return 0
  return $result
}

stage "flake evaluates"      flake_evaluates
stage "derivation evaluates" derivation_evaluates
stage "package builds"       package_builds
stage "binary present"       binary_present
stage "imports headless"     imports_headless
stage "local wow usable"     local_wow_usable

if [ $FAILED -eq 0 ]; then
  echo "all stages passed"
else
  echo "some stages failed"
  exit 1
fi
