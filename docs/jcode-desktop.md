# jcode desktop

[Jcode Desktop](https://github.com/1jehuang/jcode-desktop) is a native GPUI
client for jcode. It is built from source here, crate by crate, in the same
graph as `pkgs.jcode` (see [jcode](jcode.md#shared-crates)), and it runs that
`pkgs.jcode` for everything it spawns.
Linux only (charon, kerberos): `modules/agents/linux/jcode-desktop.nix`
installs it, so every host with the `agents` trait gets it on Linux and none on
darwin. See [macOS](#macos) for nyx.

The nix files carry no comments, so the reasons behind each setting in
`pkgs/jcode/` and `pkgs/jcode-desktop/package.nix` live here and in
[jcode](jcode.md).

## What "desktop embeds jcode" means

Nothing is linked in. Upstream's Linux tarball and `.deb` put three executables
in one directory:

```text
jcode-desktop               the GUI
jcode                       the CLI and daemon
jcode-harness-api-bridge    the SDK bridge (optional, see below)
```

and Desktop looks for `jcode` beside its own executable before `$PATH`
(`companion_executable` in `jcode-desktop-harness/src/platform.rs`). It uses
that binary for three things:

| Use | Command | When |
| --- | --- | --- |
| Daemon | `jcode serve` | only if `$XDG_RUNTIME_DIR/jcode.sock` is not accepting |
| API bridge | `jcode-harness-api-bridge`, else `jcode api-bridge` | only if `jcode-api.sock` is not accepting |
| Accounts | `jcode auth status --json`, `jcode usage --json`, `jcode auth doctor --json` | accounts UI and sidebar |
| Restart | `jcode server reload --force` | Desktop's workspace restart |

So a custom jcode inside Desktop is a symlink next to the GUI binary. This
package installs:

```text
libexec/jcode-desktop/jcode-desktop   wrapper
libexec/jcode-desktop/.jcode-desktop-wrapped
libexec/jcode-desktop/jcode  ->  pkgs.jcode/bin/jcode
bin/jcode-desktop            ->  ../libexec/jcode-desktop/jcode-desktop
share/applications/jcode-desktop.desktop
```

`current_exe()` is the wrapped file, so the sibling lookup lands on the
symlink. `makeWrapper` keeps the binary in the same directory, and a new
Desktop window relaunches through that wrapped file with the wrapper's
environment already inherited. There is no `jcode-harness-api-bridge`: without it the SDK
(`jcode-sdk/src/launch.rs`, `ensure_runtime`) falls back to `jcode api-bridge`,
the same patched binary again.

Which process starts the daemon matters more than which binary sits next to
Desktop: a daemon already running (started by a TUI client from the profile)
is reused as is. Both paths resolve to the same store path within one
generation.

## Source layout

Desktop is a separate repository, but it does not build on its own: its crates
reach 45 jcode crates (`jcode-sdk`, `jcode-base`, `jcode-core`,
`jcode-provider-core`, ...) through relative path dependencies,
`path = "../../../jcode/crates/..."`. Upstream builds from two sibling
checkouts, and so does the `graph` derivation in `pkgs/jcode/package.nix`:

```text
jcode/           the patched jcode tree
jcode-desktop/   the jcode-desktop input
Cargo.toml       one workspace over both, from combine-workspace.py
Cargo.lock       one lock over both, from align-lock.py
```

`combine-workspace.py` moves each checkout's `[workspace]` table into the
top-level manifest (members, inherited `package` and `dependencies` keys, and
desktop's `[patch.crates-io]` for GPUI) and drops both `[profile]` tables,
which only cargo reads. The relative path dependencies resolve unchanged.

Building Desktop against the patched tree matters for more than consistency:
`claude-account-failover.patch` adds the `auth.json` lock in `jcode-base`,
which Desktop also links and writes through. In the shared graph it is the
same `jcode-base` derivation.

jcode's demo assets (well over 100 MB) are excluded from the copy. No crate
either binary links reads them.

Git dependencies are pinned in `pkgs/jcode/desktop-git-hashes.json`, one entry
per repository: the gpui fork (23 crates), handterm, mermaid-rs-renderer,
gpui-thinking-orbs, and Zed's font-kit, xim, scap, wasm_thread, plus a proptest
fork. `pkgs/jcode/crate-hashes.json` holds the same hashes keyed per crate, the
form crate2nix reads.

## Keeping the two inputs compatible

The two inputs move independently and the coupling is real: Desktop `main` at
`7406154` (2026-10-11) depends on a `jcode-voice` crate that jcode only
gained after `29d17a9`, the revision it releases against.

Desktop's release workflow pins the jcode runtime it was tested with, in
`.github/workflows/cross-platform-release.yml`:

```yaml
- uses: actions/checkout@...
  with:
    repository: 1jehuang/jcode
    ref: 29d17a9aee1851d90d8a7a061d4535e2d1864994
```

`pkgs/jcode/compat.nix` reads that pin at evaluation time and refuses to
evaluate `pkgs.jcode` or `pkgs.jcode-desktop` unless both hold:

- the `jcode` input's locked revision is exactly the pin, and
- every `jcode/crates/<name>` path dependency in desktop's manifests exists in
  that jcode tree.

The pin alone is not enough. `7406154` still pins `29d17a9` while already
needing `jcode-voice`, so the second check is what catches it:

```text
error: pkgs/jcode: jcode-desktop links jcode crates that jcode 29d17a9... does not have: jcode-voice.
```

and a desktop commit pinned to another jcode fails with

```text
error: pkgs/jcode: jcode is locked at 29d17a9..., but jcode-desktop 3e44e8f is released against jcode 4a74008....
```

The check runs in `pkgs/jcode`, not only in the desktop package, because the
lock jcode is built from depends on desktop too.

Both inputs follow their default branches in `flake.nix`, and the revisions
live only in `flake.lock`. Move them with

```sh
scripts/update-jcode
```

which walks desktop's history from the newest commit, skips any commit that
links a jcode crate its own pin lacks, and locks the first match together with
the jcode revision it pins. On 2026-10-12 it skipped the six commits from the
`jcode-voice` switch onward and chose `5439b26` with jcode `29d17a9`.

`nix flake update` on its own will usually move jcode past desktop's pin, and
the next evaluation says so. If a new desktop commit moved a git dependency,
the graph build reports the new hash, and both JSON files need it.

## Build

```sh
nix build .#nixosConfigurations.charon.pkgs.jcode-desktop -L
```

The binary is `pkgs.jcode-desktop-unwrapped`, the `jcode-desktop` target of the
shared graph. `pkgs.jcode-desktop` wraps it with the layout above and the
runtime settings below. Desktop-specific settings in `pkgs/jcode/dyn.nix`:

- `crateBin` is narrowed to `jcode-desktop`, and `-C strip=symbols` applies to
  it, as for `jcode`.
- `jcode-desktop-ui` declares `crate-type = ["rlib", "cdylib"]` for upstream's
  Ctrl+R hot reload, which rebuilds the cdylib with cargo from a source
  checkout. A packaged build never does that, so the override builds the rlib
  only and the UI is linked statically.
- `JCODE_DESKTOP_VERSION` is set to the package version on `jcode-desktop-ui`,
  whose build script would otherwise call git for a `-dev.N` suffix, and
  `SOURCE_DATE_EPOCH` fixes its build timestamp.
- `yeslogic-fontconfig-sys` gets pkg-config and fontconfig, and the
  `jcode-desktop` binary gets `libxcb`, `libxkbcommon`, `alsa-lib`, fontconfig
  and freetype to link against. Everything else GPUI needs builds with the
  defaults.

Upstream's `.cargo/config.toml` (a parallel front-end rustc wrapper for debug
builds, and mold through clang) is never read: `buildRustCrate` calls rustc
directly. The GPUI view tests are not run, since they need a display and a
GPU.

## Runtime

Desktop reads its settings from the jcode config, `~/.jcode/config.toml`, under
`[desktop.*]` tables (`JCODE_HOME/config.toml` if set, or a standalone file
without the `desktop.` prefix if `JCODE_DESKTOP_CONFIG` is set). It writes its
own choices back there, such as `[desktop.appearance] theme` and
`[desktop.workspace] pinned_working_dir`. That file is reinstalled from
`modules/agents/config.toml` on every switch, so a value Desktop wrote survives
only in `config.toml.bak` until it is copied into the repo.

On launch Desktop offers a Jcode account welcome screen unless
`[desktop.workspace] account_sign_in_handled` is true or a Jcode hosted
account key exists (`JCODE_API_KEY`, or `~/.config/jcode/jcode-subscription.env`).
Claude and OpenAI logins do not count, so it appears on every machine here.
`modules/agents/config.toml` sets the flag, which is also what Desktop writes
when the screen is finished or skipped.

GPUI renders through wgpu, which dlopens Vulkan, and its Wayland backend
dlopens `libwayland-client`, and the X11 path wants libGL. None of them is
`DT_NEEDED`. Those, libGL and libxkbcommon go on the rpath of the wrapped
binary
with `patchelf --add-rpath` rather than `LD_LIBRARY_PATH`, which would leak
into every shell and agent Desktop spawns.

The wrapper sets:

| Variable | Why |
| --- | --- |
| `JCODE_DESKTOP_NO_REDIRECT=1` | A release build execs a newer copy found under `~/.local/opt/jcode-desktop` (upstream's self-updated install). That would silently replace this one. |
| `JCODE_CHECK_UPDATES=false`, `JCODE_NO_AUTO_UPDATE=1` | Same as `home.sessionVariables` in `modules/agents/jcode.nix`, for a daemon Desktop starts from a launcher that never read the shell profile. |
| `PATH` += poppler-utils | PDF previews shell out to `pdftoppm`. |

`/update` inside Desktop refuses this install (store path, not one of its
managed layouts), which is the wanted behaviour. Updates come from
`flake.lock`.

After a switch, the running Desktop still points at the previous generation's
jcode until it is restarted, and so does a running daemon or bridge. Restart
Desktop, then `jcode server reload` if the daemon should move too.

## macOS

nyx does not install it. The macOS app is a signed, notarised bundle with a
Sparkle updater, and its build shells out to `xcrun` (`build.rs` compiles an
Objective-C updater bootstrap). None of that maps onto a sandboxed nix build
without real work. The bundle uses the
same sibling lookup (`Jcode.app/Contents/MacOS/jcode`), so two workable routes
exist if it is ever wanted:

- Install the official app and make sure the nix `jcode` daemon is running
  first. Desktop then reuses it, and only its bridge and account commands run
  the bundled binary.
- Replace `Contents/MacOS/jcode` with a symlink to the profile `jcode` and
  re-sign ad hoc (`codesign --force --deep -s - Jcode.app`). Every Sparkle
  update puts the original back.
