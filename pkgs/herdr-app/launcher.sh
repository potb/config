#!@bash@/bin/bash
PATH="/etc/profiles/per-user/$USER/bin:$HOME/.nix-profile/bin:/run/current-system/sw/bin:/nix/var/nix/profiles/default/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}:@herdrCore@/bin"
export PATH

exec "${0%/*}/herdr-app" "$@"
