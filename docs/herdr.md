# herdr

herdr is the agent multiplexer, configured in `modules/dev/herdr.nix` through
Home Manager's `programs.herdr`. `settings` is written as TOML to
`~/.config/herdr/config.toml`. The `dev` set puts it, with herdr-app and its
mods, on every host used for work: charon, kerberos and nyx.

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
installed by `modules/dev/herdr.nix` through the `herdr-app` overlay in
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

## Mods and tools (herdr-app)

The herdr-app mods and helper scripts that are owned here live in
`modules/dev/herdr/mods/<name>/` and `modules/dev/herdr/tools/`. Each mod
folder and the `tools` folder are linked into `~/.config/herdr-app` with
`mkOutOfStoreSymlink`, so the links point at this checkout rather than at a
store copy. Edit the files in the repo and herdr-app picks them up without a
rebuild. Commit when the change is good.

herdr-app reloads a mod when a file in `~/.config/herdr-app/mods` changes, but
its watcher does not follow a linked folder: an edit behind the link is not
seen. Touching the link itself (`touch -h`) does trigger the reload. On Linux
the `herdr-mods-reload` user service watches the checkout with inotify and
touches the matching link after each write, so an edit reloads within about a
second. macOS has no such service yet: touch the link by hand there.

- A new mod folder needs a Home Manager switch to get its link. Edits to an
  existing mod do not.
- herdr-app writes `gpui-kit.d.ts`, `herdr.d.ts` and `jsconfig.json` into each
  mod folder on start, and Python writes `__pycache__` into `tools`. They land
  in the checkout and are ignored by `modules/dev/herdr/.gitignore`.
- herdr-app keeps the resolved path of a running mod. After a mod folder moves
  in the repo, the old path errors in `herdr-app status` until the layout block
  is given another mod and then its own again, which starts a fresh copy.
- `~/.config/herdr-app/CLAUDE.md` comes from
  `modules/dev/herdr/herdr-app-agents.md`. It tells agents working in
  herdr-app's folder which parts are links into this repo and to commit here,
  under this repo's [AGENTS.md](../AGENTS.md). herdr-app's own `AGENTS.md` next
  to it is rewritten on every start and cannot carry that.
- Mods that come with herdr-app and were never changed stay under herdr-app's
  own management in `~/.config/herdr-app/mods` and are not in this repo. Bring
  one in only after changing it, and give it a `-potb` name (`menu-potb`,
  `pane-potb`) rather than the shipped one. herdr-app treats a folder under a
  shipped name as an edited copy: each start moves it to `<name>-edited` and
  restores its own, and the next Home Manager switch then fails because the
  link's place holds a plain folder. Layouts pick a renamed clone by name:
  `"toast": "toast-potb"` and `"terminal_menu": "menu-potb"` at the layout
  root, `"mod": "pane-potb"` in a pane header.
- State that herdr-app writes (`data/`, `shared.json`, `view.json`,
  `seen.json`, the `layouts/.state` folder) stays out of the repo. So do the
  layouts, `keys.json` and `programs.json`, which herdr-app or the scripts
  rewrite in place: an atomic rewrite replaces a link with a plain file.
- After `herdr-app check ~/.config/herdr-app/mods/<name>`, also look at the
  mod in the app. `herdr-app status` lists reload errors.

### Credentials

Mods and tools never hold credentials in the repo. A fixed key, such as the
Linear API key that `tools/scan-ship.py` reads, is encrypted with sops in
`secrets/herdr.yaml` for the age key in `~/.config/sops/age/keys.txt` (listed in
`.sops.yaml`). On charon, `hosts/charon/modules/herdr-secrets.nix` has
sops-nix decrypt it at login into the user runtime directory and link it to the
path the script already reads (`~/.config/herdr-app/data/linear/key`).

To add a secret, run `sops secrets/herdr.yaml`, add a key, and add a matching
`sops.secrets.<key>.path` in that host module. Session tokens that a tool gets
by signing in, such as Rakazo's in `~/.local/share/rakazo/session.json`, are
state, not configuration, and stay out of Nix.

## Claude sessions inside herdr-core

herdr-core starts a long-lived holder process that owns every terminal, and the
holder keeps the environment of whatever shell started it. If that shell
belonged to a Claude Code session, every terminal inherits `CLAUDECODE=1`,
`CLAUDE_CODE_CHILD_SESSION=1`, that session's ID and its `CLAUDE_PID`. Claude
Code treats a session with `CLAUDE_CODE_CHILD_SESSION` set as a child and does
not persist it: no transcript in `~/.claude/projects` and no entry in
`~/.claude/history.jsonl`. This happened from Nov 10 to Nov 12, 2026, after the
holder was started from a Claude session on Nov 9.

`modules/dev/herdr.nix` adds a zsh guard for this. In a herdr-core terminal
(`HC_RUNTIME` set), when `CLAUDE_PID` names a process that no longer exists,
the shell unsets the inherited Claude variables before anything runs. Shells
that Claude spawns for its own tools keep their variables, since their
`CLAUDE_PID` is alive.

The guard only helps shells started after the fix. The cleanest reset is to
restart herdr-core from a plain shell (`herdr-core server restart`), which ends
every running terminal.
