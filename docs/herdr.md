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

## Images (Kitty graphics)

herdr renders Kitty graphics from pane output into the outer terminal (Ghostty).
`terminal.kitty_graphics = true` is the default on 0.9.x and is pinned here so a
changed default cannot silently turn images off. The older
`experimental.kitty_graphics` key is still accepted, and `terminal.*` wins.

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

## Desktop app (herdr-app)

herdr-app, the Herdr desktop window, comes from `numtide/llm-agents.nix` and is
installed by `modules/base/packages.nix` through the `herdr-app` overlay in
`overlays/custom-packages.nix`. On Linux the overlay passes the upstream package
through unchanged, since it already installs a `.desktop` file and an icon.

On macOS upstream installs only `bin/herdr-app`, which Spotlight and the Dock
never see. `pkgs/herdr-app` adds `Applications/Herdr.app`, laid out like the
bundle upstream's `scripts/package` builds: the same `Info.plist` keys
(`dev.herdr.app`), `Herdr.icns` from the upstream source, LICENSE and
THIRD-PARTY-NOTICES. Home Manager's `copyApps` copies it to
`~/Applications/Home Manager Apps`, where Spotlight indexes it.

- The real binary (upstream's `.herdr-app-wrapped`) lives in
  `Contents/MacOS/herdr-app`, not upstream's `wrapProgram` script. macOS finds
  the bundle, and with it the name and icon, from the executable's own path.
  If upstream stops using `wrapProgram`, the `cp` fails the build.
- `Contents/MacOS/Herdr` (`pkgs/herdr-app/launcher.sh`) is the bundle
  executable. LaunchServices starts apps with launchd's minimal PATH, so it puts
  the Nix profiles first for the terminals and agents the app spawns. herdr-core
  goes last, as in upstream's wrapper, so a core the user installed wins.
  Without any core on PATH the app would `curl | sh` one.
- The launcher runs the binary next to itself, so the copy in `~/Applications`
  runs its own binary rather than the store one.
- `bin/herdr-app` execs the same launcher, so the CLI (`herdr-app ls`,
  `herdr-app status`) uses the bundled binary too.

The bundle is ad hoc signed only through the binary's own linker signature,
which is enough to run it locally.
