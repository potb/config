#!/usr/bin/env bash
# cargo-off — run a cargo command on charon instead of this machine.
#
# Usage:
#   cargo-off check
#   cargo-off clippy --all-targets
#   cargo-off test -p jcode-tui
#   cargo-off build --release --target aarch64-unknown-linux-gnu
#
# Source is rsynced to charon and the command runs there; nothing is copied
# back. Artifacts are Linux binaries and stay on charon by design, so this is
# for check/clippy/test feedback, not for producing runnable local binaries.

set -euo pipefail

REMOTE="${CARGO_OFF_REMOTE:-potb@172.20.10.10}"
SSH_KEY="${CARGO_OFF_KEY:-$HOME/.ssh/id_ed25519}"

# One multiplexed connection for the rsync and the command, so a run pays a
# single TCP and key-exchange round trip.
CONTROL="$HOME/.ssh/cargo-off-%r@%h:%p"
SSH_OPTS=(
  -o IdentityAgent=none
  -o IdentitiesOnly=yes
  -i "$SSH_KEY"
  -o ControlMaster=auto
  -o "ControlPath=$CONTROL"
  -o ControlPersist=10m
)

if [ $# -eq 0 ]; then
  echo "usage: cargo-off <cargo-subcommand> [args...]" >&2
  exit 2
fi

# Anchor on the workspace root, not $PWD: running from inside a member crate
# must still sync the whole workspace, or path dependencies break remotely.
if ! root="$(cargo locate-project --workspace --message-format plain 2>/dev/null)"; then
  echo "cargo-off: not inside a cargo workspace" >&2
  exit 1
fi
root="$(dirname "$root")"
project="$(basename "$root")"
dest="\$HOME/cargo-off/$project"

# rsync only creates the final path component, so the per-project parent has
# to exist first. Doing it over the shared control socket costs no extra
# handshake, and unlike rsync's --mkpath it does not require rsync >= 3.2.3 on
# both ends.
ssh "${SSH_OPTS[@]}" "$REMOTE" "mkdir -p $dest"

# --delete keeps a removed local file from lingering remotely and silently
# satisfying a stale `mod` declaration.
#
# target/ is excluded deliberately: it holds host-architecture artifacts that
# would be useless remotely, and on a large workspace it dwarfs the sources.
# charon keeps its own target/ in the synced directory, which is what makes
# the second run incremental.
rsync -az --delete \
  --exclude '/target' \
  --exclude '/.git' \
  --exclude '/.direnv' \
  --exclude '/result' \
  --exclude '/result-*' \
  --exclude '/.tmp' \
  --exclude '/tmp' \
  -e "ssh ${SSH_OPTS[*]}" \
  "$root/" "$REMOTE:cargo-off/$project/"

# Quote each argument so a remote bash -lc sees exactly what the user typed.
remote_args=""
for arg in "$@"; do
  remote_args+=" $(printf '%q' "$arg")"
done

exec ssh "${SSH_OPTS[@]}" -t "$REMOTE" \
  "cd $dest && exec cargo$remote_args"
