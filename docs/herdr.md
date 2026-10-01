# herdr

herdr is the agent multiplexer, configured in `modules/base/herdr.nix` through
Home Manager's `programs.herdr`. `settings` is written as TOML to
`~/.config/herdr/config.toml`. The `base` set puts it on every host.

## Theme

Stylix has no herdr target, so nothing themes it automatically. The module sets
`theme.name = "catppuccin-latte"`, herdr's built-in theme matching the
`catppuccin-latte` base16 scheme that Stylix uses (see `modules/gui/theme.nix`).

The two are not linked. If the Stylix scheme changes, change herdr's theme name
to match. The `terminal` theme, which follows the host terminal's ANSI palette,
was tried and rejected because it did not look right.

If Stylix gains a herdr target, drop the theme setting and let the target own it.
Per-token overrides are available under `theme.custom.*` if a closer match to
the base16 scheme is ever wanted.

## Updates

herdr is updated through nix only, by bumping nixpkgs (`nix flake update nixpkgs`).

herdr cannot replace its own binary here: it detects a `/nix/store` install and
`herdr update` answers "self-update is disabled for Nix installs". What remains
is the background check, which only logs and shows a notice that a newer
version exists. The module turns it off:

- `update.version_check = false` stops the check against herdr.dev for new
  versions.
- `update.manifest_check = false` stops the download of remote agent-detection
  manifests. Bundled manifests and local overrides still apply.

Checked on 0.9.1 with two isolated servers started from a config with the keys
off and a config without them. Only the second logged `update.available`
within seconds of starting. The manifest check was not observed in either, it
runs on a slower cadence, so that key is validated by `herdr config check` and
the documentation only.

## Onboarding

`onboarding = false` skips herdr's first-run setup, since the config is owned by
nix.

## Validating a change

`herdr config check` validates a config file. Point it at the generated one with
`HERDR_CONFIG_PATH`, for example the store path of `herdr-config.toml` built
from `home-manager.users.potb.xdg.configFile."herdr/config.toml".source`.
