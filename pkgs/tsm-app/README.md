# tsm-app derivation

TradeSkillMaster Desktop App for Linux, packaged from
[exceptionptr/tsm-app-linux](https://github.com/exceptionptr/tsm-app-linux).

## Why the app exists

WoW's Lua sandbox has no network access, so the TSM addon cannot fetch the
region-wide auction data its pricing model depends on. This app authenticates
against the TSM API, downloads the data, and writes `AppData.lua` into the
addon directory, where the addon reads it at game load.

## Packaging notes

APScheduler 4 is built here rather than taken from nixpkgs. The project needs
`>=4.0.0a5,<5` and nixpkgs ships 3.11.2, whose API is incompatible. The 4.x
line has only ever published alphas, so upstream nixpkgs is unlikely to carry
one.

`dontWrapQtApps` is set because `buildPythonApplication` already produces the
Python wrapper, and the Qt wrapper hook would wrap it a second time.

The version is passed in from the overlay and re-exported as
`HATCH_VCS_PRETEND_VERSION`. The upstream build reads its version from git
metadata via `hatch-vcs`, which is absent from the flake input's source tree.

## Feedback loop

`./check.sh` runs five stages in cost order and prints one PASS/FAIL line each:

| Stage | Catches |
| --- | --- |
| flake evaluates | syntax errors, missing inputs |
| derivation evaluates | bad `callPackage` arguments, missing attributes |
| package builds | compile failures, failing upstream tests |
| binary present | wheel packaging that ships no entry point |
| imports headless | missing runtime dependency, which Nix cannot detect at build time |

The last stage matters most. Nix does not resolve Python imports while
building, so a package with an incomplete `dependencies` list builds green and
fails at first launch.

Pass `--keep-going` to run every stage instead of stopping at the first
failure.

## Runtime configuration

Auto-detection scans Wine, Lutris, Faugus, and Steam's `steamapps/common`.
A Proton install lives under `steamapps/compatdata/<id>/pfx/`, which is not
scanned, so that path must be added by hand under Settings -> WoW
Installations.

## Security

The TSM API serves `app-server.tradeskillmaster.com` over plain HTTP, which is
upstream's design and applies equally to the official Windows client. Session
tokens and downloaded addon zips are therefore unauthenticated in transit.
Zip extraction is guarded against path traversal, so a hostile archive stays
within the AddOns directory. Only the Keycloak login endpoint uses HTTPS.
Credentials are stored via `keyring`, not on disk in plaintext.
