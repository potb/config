# Wispr Flow

Wispr Flow ships only for macOS and Windows. charon runs it from the Windows
installer, repackaged by `pkgs/wispr-flow` with the know-how of the unofficial
[wispr-flow-linux](https://github.com/wispr-flow-linux/wispr-flow-linux)
project and its clean-room [helper](https://github.com/wispr-flow-linux/helper),
both pinned as flake inputs. The trait lives in
`modules/desktop-apps/linux/wispr-flow.nix` and only applies where the package
builds (x86_64-linux), so kerberos skips it without a host override.

## How the package is built

The build is pure: no `--impure`, no hand-supplied installer.

1. The installer URL and sha256 come from the project's
   `scripts/setup/installer-pin.sh`, read at evaluation time, so the installer
   is an ordinary fixed-output fetch. Bumping the `wispr-flow-linux` input to a
   new release tag bumps Wispr Flow with it.
2. The Squirrel `.exe` is unpacked to the Electron payload, and `app.asar` is
   extracted.
3. The project's own `step3_patch_bundle` (sourced from
   `scripts/build-linux.sh`) runs the upstream tripwire check and then all
   thirteen patches that give the minified bundle a Linux code path. Reusing
   the driver means the list of patches cannot drift from upstream's.
   `verify-patches.sh` then refuses an asar that misses any marker.
4. The Windows `node_sqlite3.node` is replaced by one compiled from the
   `sqlite3` npm tarball against the nixpkgs Electron 42 headers (see below).
   The Windows-only crypt32, Jabra and roots binaries are dropped, and the
   Linux Jabra headset bridge is unpacked from the asar and patched by
   `autoPatchelfHook`.
5. The helper is built from source with `rustPlatform` and staged at
   `resources/Release/wispr-flow-linux-helper`, where the patched bundle looks
   for it.
6. The app runs on the stock nixpkgs `electron_42`, with no copy of the 250 MB
   Electron binary and no FHS sandbox (see below).

`wispr-flow --doctor` is the project's diagnostic with two checks replaced for
NixOS: the sandbox check looks for unprivileged user namespaces instead of a
setuid `chrome-sandbox`, and the desktop entry check looks on `XDG_DATA_DIRS`
and also reports who handles `wispr-flow://` links.

## Running on the nixpkgs Electron

Electron derives `process.resourcesPath` and `app.isPackaged` from its own
executable. The app needs both to point at its own tree: `resourcesPath` to
find `migrations/`, `assets/` and the helper, `isPackaged` to choose the
packaged migrations path. With `isPackaged` false, zero migrations run and
every query fails with "no such table". The upstream packages solve this by
copying the Electron binary next to the resources and renaming it; the
upstream Nix expression copies it into the store and then wraps everything in
`buildFHSEnv`.

Here a ten-line entry module (`resources/entry`) is what Electron launches. It
redefines `process.resourcesPath` and `app.isPackaged` and then requires
`app.asar`. Its `package.json` carries the app's name and
`desktopName: wispr-flow.desktop`, which makes the Wayland app id
`wispr-flow` and lets the app find its desktop file.

## Traps

- **The native sqlite addon silently used the wrong sqlite.** nixpkgs'
  `node-gyp` wrapper forces `npm_config_nodedir` to the nixpkgs Node.js, so
  `--nodedir` is ignored and the addon is compiled against Node's headers. On
  top of that, nixpkgs Node.js ships `include/node/sqlite3.h` (3.53), which
  shadows the amalgamation `sqlite3` 5.1.7 bundles (3.44.2). The package runs
  npm's bundled `node-gyp.js` with `npm_config_nodedir` set to
  `electron.headers`, and links with `-Bsymbolic` so the addon keeps its own
  sqlite even though the nixpkgs Electron already has `libsqlite3.so` loaded.
  The install check fails the build if the addon reports anything but 3.44.2.
- **The app loads only `node_sqlite3`.** The upstream scripts also rebuild
  `better-sqlite3-multiple-ciphers` with a V8 patch, but no 1.6.1102 bundle
  references it.
- **`asar pack --unpack-dir` globs skip dot directories.** `**/x` never
  matches under `.webpack`, so the Jabra directory is unpacked by its literal
  path, and the build checks the binary landed outside the asar.
- **The status pill.** On Hyprland the "Flow Status Indicator" window maps
  floating on one workspace. The trait adds a window rule that pins it and
  keeps it from taking focus. Match on `initial_title`, because the title
  later changes to "Status".

## Runtime requirements

- `/dev/uinput` writable for text injection. charon already grants it through
  `hardware.uinput` (the `uinput` group); the package also ships the upstream
  udev rule, installed by `services.udev.packages`, which adds a `uaccess`
  ACL for the active session.
- `/dev/input/event*` readable for push-to-talk. The helper reads keyboards
  through evdev. The `uaccess` rule above grants it to the active session
  once applied (new devices, or after `udevadm trigger`); without it the
  helper logs "no readable keyboard" and the shortcut never fires.
- AT-SPI for active-app detection on Hyprland, already enabled by the
  computer-use trait.

Login goes through the browser with a device code and a server-sent event
stream back to the app, so it works without the `wispr-flow://` handler. The
handler is still registered for the app's other deep links.

## Upstream state (2026-10-09)

The wispr-flow-linux flake (`v1.0.4+wispr1.6.1102`) does not build: its
derivation runs 2 of the 13 patches and `verify-patches.sh` rejects the
result, it requires `WISPR_FLOW_EXE` and `--impure`, and it ships the Windows
`node_sqlite3.node`, which crashes the main process with "invalid ELF header"
before any window opens.
