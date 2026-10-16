# jcode

`jcode` is built from source by this repository rather than installed by its
own installer script. The flake input `jcode` tracks
[1jehuang/jcode](https://github.com/1jehuang/jcode) master and is pinned in
`flake.lock`, so a rebuild produces the same binary until the input is updated
deliberately.

The build graph is generated at build time by
[crate2nix](https://github.com/nix-community/crate2nix) running inside a
derivation, wired up with [drowse](https://github.com/figsoda/drowse). Nothing
generated is committed to this repository.

## Why not buildRustPackage

`buildRustPackage` (and `naersk`/`crane` in their default modes) compile the
whole dependency graph inside one derivation. A one-character change anywhere
re-runs the entire compile, and nothing in the graph is shared with other
projects.

crate2nix reads `Cargo.lock` and emits one `buildRustCrate` derivation per
package. In this workspace that is 861 derivations: the 83 workspace members
plus every crates.io and git dependency. Each is an independent store path, so
it is cached, substitutable, and reusable on its own. Editing a leaf crate
rebuilds that crate and its dependents only.

## Why dynamic derivations

crate2nix offers two ways to get those derivations, and both used to be
unpleasant:

- Committing a generated `Cargo.nix`. This repository did that until the
  dynamic build replaced it. The file was 34k lines, it dominated diffs, and it
  silently went stale: when upstream added a `toml` dependency to
  `jcode-selfdev-types`, the checked-in graph still described the old
  dependency set and rustc failed with `E0433: cannot find module or crate
  toml`. Recovering meant checking out jcode at the locked revision, running
  `crate2nix generate` by hand, and copying the result back.
- Import from derivation. Always in sync, but it interleaves evaluation and
  realisation: evaluation blocks on a build, which serialises the whole
  rebuild.

Dynamic derivations remove the choice. A derivation may output another
derivation, and `builtins.outputOf` refers to the result of building it. So
crate2nix runs in the sandbox, its `Cargo.nix` never leaves that sandbox, and
evaluation never waits for it. The feature is experimental; see
[RFC 92](https://github.com/NixOS/rfcs/blob/master/rfcs/0092-plan-dynamism.md)
and its [tracking issue](https://github.com/NixOS/nix/issues/6316).

## Layout

| Path | Purpose |
| --- | --- |
| `pkgs/jcode/package.nix` | Feature, version, and compatibility guards, the shared graph derivation, and one `outputOf` generator per binary. Returns `jcode`, `jcode-desktop-unwrapped`, `graph`, and `compat`. |
| `pkgs/jcode/dyn.nix` | The expression evaluated inside each generator. Per-crate sources, native dependencies, compiler settings, and the unified feature root. |
| `pkgs/jcode/compat.nix` | The evaluation-time check that the jcode and jcode-desktop inputs belong together. See [jcode desktop](jcode-desktop.md). |
| `pkgs/jcode/combine-workspace.py` | Merges the jcode and jcode-desktop checkouts into one cargo workspace. |
| `pkgs/jcode/align-lock.py` | Resolves that workspace's `Cargo.lock` offline, preferring every version jcode locks. |
| `pkgs/jcode/members.py` | Writes `members.json`, the workspace member to directory map `dyn.nix` reads. |
| `pkgs/jcode/git-hashes.json`, `desktop-git-hashes.json` | Fixed-output hashes for each input's git dependencies, used to vendor its `Cargo.lock`. |
| `pkgs/jcode/crate-hashes.json` | The same git dependencies keyed the way crate2nix expects. |
| `scripts/update-jcode` | Moves both flake inputs to a matching pair. |
| `shared/nix-features.nix` | The experimental features this configuration enables, read by both `modules/base/nix.nix` and this package. |

The overlay in `overlays/custom-packages.nix` exposes the package set as
`pkgs.jcode-build`, and from it `pkgs.jcode` and `pkgs.jcode-desktop-unwrapped`.
`modules/agents/jcode.nix` installs `pkgs.jcode` into the user profile.
No service supervises the daemon. The first client spawns it, and it resolves
its binary through the channel links under `~/.jcode/builds` (`shared-server`,
then `stable`) before falling back to its own executable. A nix install has no
use for that tree, so it should not exist: with it gone, clients, the daemon
and the menu bar helper all run the profile binary. A leftover tree from a
release install or self-dev build silently wins over the nix package, and
`jcode server reload` cannot move off it, because its downgrade guard compares
mtimes and every store path is dated 1970. Stop the daemon, then remove
`~/.jcode/builds`.

## How a build runs

jcode and [jcode desktop](jcode-desktop.md) are built from one crate graph, so
a crate both binaries link is one derivation and compiles once.

1. `package.nix` checks the guards below and vendors each input's
   `Cargo.lock` with `rustPlatform.importCargoLock`.
2. The `graph` derivation copies the patched jcode tree and the jcode-desktop
   tree side by side, merges them into one cargo workspace, resolves one
   `Cargo.lock` for it (see [Lock alignment](#lock-alignment)), and runs
   `crate2nix generate` over the result. Its output is the workspace, the
   generated `Cargo.nix`, `members.json`, `alignment.json`, and `dyn.nix`.
3. One drowse generator per binary: a content-addressed derivation named
   `jcode-0.94.0.drv` or `jcode-desktop-unwrapped-0.5.1.drv` whose build runs
   `nix-instantiate` over `dyn.nix` inside the graph output.
4. `dyn.nix` imports `Cargo.nix`, applies the crate overrides, resolves
   features once for both roots, and yields the requested binary.
5. `builtins.outputOf` turns each generator's output into a normal store path
   dependency, and `runCommand` symlinks it so the final path carries a
   readable name.

Step 2 is serial and takes about two minutes cold, most of it the lock
resolution and crate2nix. It reruns when either input, a patch, or one of the
scripts changes. Step 3 is a few seconds per binary. Steps 4 and 5 are the
usual parallel crate builds.

`dyn.nix` is read from the graph output and evaluated in the sandbox against
`<nixpkgs>`, so it cannot import anything else from this repository. Settings
that need to cross that boundary (`optLevel`, `codegenUnits`, the feature
roots, the build target, and the output name) are passed as a JSON file through
`passAsFile`.

## Shared crates

Two things decide whether a crate both binaries use is one derivation or two:
its version, and its enabled features. `buildRustCrate` hashes the crate name,
version, feature flags, and the metadata of every dependency into the
derivation, so a single differing feature anywhere below a crate splits it.

Versions come from one `Cargo.lock` for both, described next.

Features are resolved once. `dyn.nix` adds a synthetic `nix-build-roots` crate
that depends on `jcode` (with `rootFeatures`, no defaults) and on
`jcode-desktop` (defaults), and builds both binaries out of that one resolution,
the same way cargo unifies features across a workspace. Resolving each binary on
its own was measured first: only 193 of the 407 crates both graphs contain came
out identical, because desktop turns on extra features of shared crates (for
example `jcode-base`'s `voice-capture`, `arboard`'s Wayland clipboard,
`async-compression`'s bzip2). With one resolution all of them match.

The cost is that jcode is compiled with the union of features. It links
`libxcb` and `alsa-lib` as a result, which the `jcode` override provides.
Darwin has no desktop root, so its jcode graph is resolved for jcode alone,
although its lock is still the aligned one.

Measured on charon at jcode `29d17a9` and desktop `5439b26`:

| | crate derivations |
| --- | --- |
| jcode | 699 |
| jcode desktop | 821 |
| shared | 572 |
| shared jcode workspace crates | 45 of 45 desktop links |

Adding a one-line change to `jcode-base` through a patch rebuilds 18 crates
for both binaries together, in 204 s: `jcode-base` once, the jcode crates
above it, and the desktop crates that depend on them. Every other crate,
including the GPUI stack, comes from the store.

## Lock alignment

jcode and jcode desktop each ship a `Cargo.lock`, and the two drift: at the
revisions above, 188 crate names were locked to versions the other side did
not use. One workspace needs one lock, and the useful one keeps jcode's
versions wherever it can, so that jcode itself is built from what upstream
tested.

`align-lock.py` builds it offline from the two vendor directories:

1. It offers cargo only the versions jcode locks for every crate jcode uses,
   plus desktop's versions for crates only desktop uses, and seeds the lock
   from both files.
2. When cargo cannot resolve, it reads the crate that failed from the error
   and also offers desktop's version of it. It repeats until the workspace
   resolves.
3. It then tries `cargo update --precise` back down to jcode's version for
   every crate that ended up with another one, and keeps each that resolves.

The result at the revisions above: 790 registry crates at exactly jcode's
version, and 56 crates where the lock also carries a second version. 25 jcode
versions are replaced outright, all patch or minor bumps forced by a
requirement on the desktop side, for example `serde_json = "1.0.151"` in
every desktop crate, `futures ^0.3.34` and `serde_json ^1.0.144` in GPUI,
`anyhow ^1.0.103` in handterm, and `unicode-properties = "=0.1.3"` in
`gpui_web`. The full list is in `alignment.json` in the graph output.

Git dependencies are not aligned, since they are pinned by revision. jcode and
desktop use different revisions of `mermaid-rs-renderer` 0.3.1, so the lock
carries both and crate2nix builds both.

## Guards

The package refuses to evaluate rather than fail in a confusing way later.

`shared/nix-features.nix` is the single declaration of the experimental
features this configuration enables. `modules/base/nix.nix` writes them into
`nix.settings.experimental-features` on nixos and into
`determinateNix.customSettings.extra-experimental-features` on darwin, and
`package.nix` asserts that
`ca-derivations`, `dynamic-derivations`, and `recursive-nix` are all still
there. Removing one from that file fails evaluation with a message naming the
missing feature, instead of producing a daemon that cannot build this package.

Both platforms need the full `base ++ dynamic` set, not just `base`. Darwin
writes `/etc/nix/nix.custom.conf` through the determinate module, which is a
different option than the nixos `nix.settings` path, so the two lists have to be
kept in step deliberately. When darwin was left on `base` alone,
`builtins.outputOf` was missing from `builtins` and every evaluation of the
darwin system failed in `pkgs/jcode/package.nix` with `attribute 'outputOf'
missing`. The daemon also needs `recursive-nix` in `system-features` before it
will schedule the generator build locally.

Darwin also sets `lazy-trees = false`, which Determinate Nix otherwise defaults
to true. The drowse generator calls `builtins.appendContext` on a flake input
path through its `__pathToString` helper, and under lazy trees that path is
never realised in the store, so evaluation fails with `path '...-source' is
required, but there is no substituter that can build it`. The setting is scoped
to darwin because only Determinate ships that default.

Two version bounds:

- Below nix 2.28 the package refuses to build. Dynamic derivations need a
  recent enough daemon.
- At nix 2.36 and above the package refuses to build on purpose. That release
  is where dynamic derivations may stabilise and where `builder-rpc-v0` lands,
  the minimal daemon interface that replaces `recursive-nix`. Reaching it
  should prompt a review of this package rather than a silent upgrade: both the
  `recursive-nix` dependency and the crate2nix generator may be removable. Once
  reviewed, raise `reviewNix` in `package.nix`.

Note that `builtins.tryEval` cannot soften any of this. A disabled experimental
feature aborts evaluation outright rather than producing a catchable error, and
no builtin reports which features are active. That is why the feature set is
declared in the repository and asserted against, not probed.

## Source granularity

Each crate gets the workspace `Cargo.toml` and `Cargo.lock`, its checkout's
`Cargo.toml`, and its own directory, which is what keeps the derivations
independent. A few crates read files outside their own directory:

- `jcode-build-meta` parses the root `Cargo.toml` and shells out to `git` for the
  hash, date, tag, and changelog. The store has no git repository, so the
  override pins `JCODE_BUILD_GIT_*` to fixed values. This also keeps the build
  reproducible: otherwise the embedded version would depend on the checkout's git
  state rather than on the source contents.
- `jcode-app-core`'s build script embeds `README.md` and every `docs/*.md` file
  into its documentation corpus, so its source tree includes both.
- `jcode-setup-hints` uses `include_bytes!` on
  `assets/app-icons/Jcode.icns`. Only that subdirectory is added, not the 113 MB
  of demo assets.
- The jcode desktop crates embed icons, previews, and applets with
  `include_bytes!` and `include_str!` from `jcode-desktop/assets` and
  `jcode-desktop/applets` (1.4 MB together). `jcode-desktop-api` reads the
  desktop `Cargo.toml` in a test, and `jcode-desktop-ui` embeds
  `CHANGELOG.md`. `extraPathsFor` in `dyn.nix` lists each.

Because the shared lock is part of every crate's source, a change that moves
the lock (a new jcode or desktop revision) rebuilds every workspace crate, as it
did before. A patch moves no lock entry, so it rebuilds only what it touches.

Unrelated repository content never becomes a build input, so touching it cannot
invalidate a crate derivation.

## Features

`rootFeatures` is `["pdf" "embeddings"]`. Upstream's `default` also includes
`bedrock`, which pulls in the AWS SDK stack for live Bedrock support. Nothing
here uses it, so it is left out of the jcode root. jcode desktop's crates still
enable it through their `jcode-base` dependency, so the unified build carries
it for both.

## Compiler tuning

`buildRustCrate` hardcodes `-C opt-level=3 -C codegen-units=1` for release
builds. Neither matches this project: jcode's `[profile.release]` specifies
`opt-level = 1` and `codegen-units = 256`. `package.nix` therefore passes
`optLevel = 1` and `codegenUnits = 16` to every workspace crate.

`codegen-units` matters more than the crate split here. The dependency graph ends
in a chain (`jcode-base` -> `jcode-app-core` -> `jcode-tui` -> `jcode`) of crates
between 113k and 212k lines each. Nothing in that chain runs in parallel with
anything else, so at `codegen-units = 1` the build is four long single-threaded
rustc invocations and `max-jobs` cannot help. Splitting each crate into 16
codegen units is the only way to use more than one core on that critical path.

Measured on charon (24-core i9-14900K), rebuilding all 83 workspace crates from a
cleared store:

| configuration | wall time | speedup | binary |
| --- | --- | --- | --- |
| `opt-level=3`, `codegen-units=1` (buildRustCrate default) | 545 s | 1.00x | 120.9 MB |
| `opt-level=1`, `codegen-units=1` | 366 s | 1.49x | 124.2 MB |
| `opt-level=3`, `codegen-units=16` | 243 s | 2.24x | 143.6 MB |
| `opt-level=1`, `codegen-units=16` | 151 s | 3.61x | 140.1 MB |

The binary is 16% larger than the `codegen-units = 1` build because less inlining
happens across unit boundaries. Upstream's own release profile uses 256 units, so
16 remains the more conservative setting.

Sweeping the remaining knobs at `max-jobs = 8`, `cores = 4` shows that 16 is
already at the knee:

| configuration | wall time | binary |
| --- | --- | --- |
| `codegen-units=16` | 149 s | 140.1 MB |
| `codegen-units=32` | 157 s | 142.1 MB |
| `codegen-units=64` | 153 s | 143.8 MB |
| `codegen-units=256` | 153 s | 145.2 MB |
| `codegen-units=16` + mold | 153 s | 149.8 MB |
| `opt-level=0`, `codegen-units=16` | 72 s | 208.8 MB |

Past 16 units the wall time is flat within noise while the binary keeps growing.
Linking with mold makes no difference either: rustc spends its time in codegen,
not in the linker, and only a handful of the 861 derivations produce a binary at
all. `opt-level = 0` halves the build again but produces a 209 MB unoptimised
binary, which is a development trade rather than a default; pass `optLevel = 0`
to `package.nix` when that is what is wanted.

## Output size

jcode's root crate declares seven binaries, and `buildRustCrate` builds every
one whose required features are enabled. Three of them (`jcode`,
`jcode-harness`, `test_api`) came out of a default build, for 211 MB in the
store, when only the first is wanted here. The override narrows `crateBin` to
`jcode` alone.

`[profile.release]` sets `debug = 0`, which omits debug info but keeps the
symbol table: 140 MB of binary, 28 MB of it symbols. Passing `-C strip=symbols`
for this crate leaves 112 MB.

| output | size |
| --- | --- |
| three binaries, unstripped | 211 MB |
| `jcode` only, unstripped | 134 MB |
| `jcode` only, stripped | 107 MB |

Stripping applies to the final binary only. Every library crate keeps its
symbols, so the rlibs stay linkable and no dependent derivation is invalidated.

## Scheduling

`max-jobs` and `cores`, measured with the tuned profile:

| max-jobs | cores | wall time |
| --- | --- | --- |
| 4 | 8 | 171 s |
| 2 | 4 | 170 s |
| 16 | 2 | 152 s |
| 8 | 4 | 150 s |

The spread is 14%, far smaller than the 3.6x from compiler flags, and for the
same reason: the critical path is a chain of four crates, so extra concurrent
derivation slots have little to work with. Dropping from 4x8 to 2x4 costs one
second, so low `max-jobs` settings on smaller machines are close to free for this
workload and memory pressure is the better reason to choose them.

## Native dependencies

Crates with a `build.rs` that compiles C get their tooling from `dyn.nix`,
layered on top of `pkgs.defaultCrateOverrides`:

- `aws-lc-sys` (the rustls backend): cmake and perl.
- `openssl-sys`: pkg-config and the nixpkgs OpenSSL, replacing the vendored build
  selected by the `linux-compat-vendored-openssl` feature.
- `libsqlite3-sys`: the system SQLite instead of the bundled amalgamation.
- `onig_sys` (via syntect), `tikv-jemalloc-sys`, `fontdb`: pkg-config, perl, and
  fontconfig as required.

## Caching

Crate tarballs and nixpkgs dependencies substitute normally. The 900 crate
derivations do not: no public cache carries `buildRustCrate` outputs built with
these overrides, and that was equally true of the committed-`Cargo.nix` build.
Local store reuse is what makes iteration cheap, and it works as usual.

Remote caching is weaker than for an ordinary package. The final store path is
only known after the generator is realised, so another machine cannot
substitute it by path from an evaluation alone. With one machine per
architecture this costs nothing.

## Update checks are off

A nix-built jcode is not a release build: nothing sets `JCODE_RELEASE_BUILD`,
and `jcode-build-meta` derives no release semver from the pinned
`JCODE_BUILD_GIT_*` values, so `is_release_build()` is false. The background
update check in `src/cli/startup.rs` therefore takes its source-build branch,
which asks `hot_exec::check_for_updates()` to compare a jcode git checkout
against its upstream. There is no checkout: the binary lives in the store, and
`get_repo_dir()` finds nothing from `JCODE_REPO_DIR`, the executable's
ancestors, or the working directory. The check returns `None`, which the TUI
renders as:

> Source update check failed: unable to compare the source checkout with its
> upstream. The repository or upstream may be unavailable, or git fetch may
> have failed.

Nothing was broken; this configuration simply has no use for the check, since
the binary only changes when `flake.lock` does. `modules/agents/jcode.nix`
turns it off with two environment variables rather than a config file, so the
setting cannot be lost to a live edit of `~/.jcode/config.toml`:

- `JCODE_CHECK_UPDATES=false` overrides `features.check_updates`, which is what
  gates the background check.
- `JCODE_NO_AUTO_UPDATE=1` covers `update::should_auto_update()`, the
  release-channel installer path, in case a release build ever runs here.

Both are set through `home.sessionVariables`, which reaches interactive shells
and everything they launch, including the daemon a client spawns.

Setting `check_updates = false` in `~/.jcode/config.toml` has the same effect
for shell-launched sessions. It is not used here because that file is seeded,
not managed, so an edit through the UI would silently win.

## MCP servers and secrets

`modules/agents/jcode/mcp.json` is seeded into `~/.jcode/mcp.json` like the
rest of the seed tree. It holds no secrets. The Exa server reads its API key
at launch from `~/.config/sops-nix/secrets/exa-api-key`, which the Home
Manager sops module decrypts from `secrets/jcode.yaml` on every activation.

The recipients of `secrets/jcode.yaml` are the admin age key plus each
machine's user SSH key (`~/.ssh/id_ed25519`, listed in `shared/keys.nix`)
converted with `ssh-to-age`. A new machine needs its key added to
`.sops.yaml` and the file re-keyed with `sops updatekeys secrets/jcode.yaml`.

The TypeSafe key for Jev memory recall is rendered as `typesafe.env` into
jcode's provider config directory. jcode resolves that through the platform
config dir, so it is `~/.config/jcode` on Linux but
`~/Library/Application Support/jcode` on macOS. Rendering it to `~/.config`
on a Mac leaves jcode reporting "No credential for the selected Jev provider
typesafe".

The Linear and Sentry servers are remote MCP endpoints bridged through
`mcp-remote`, which handles OAuth in the browser on first use and caches the
token under `~/.mcp-auth`. Neither needs a secret in this repo.

## Computer use on Linux

jcode ships desktop control only for macOS (`macos_computer_use`). Linux
machines get it from
[computer-use-linux](https://github.com/agent-sh/computer-use-linux), packaged
in `pkgs/computer-use-linux` and enabled by `modules/agents/linux/computer-use.nix`.
The seeded `mcp.json` is generated rather than copied: on Linux the
`computer-use` server is merged into the shared file, so nyx never tries to
launch a binary it cannot run.

It was picked over cua-driver, zavora-ai/computer-use-mcp and da-mcp because
it is the only one whose pointer is exact on Hyprland without an experimental
compositor plugin, and it still covers GNOME, KDE, i3, COSMIC and X11.

How each capability is served on Hyprland:

| Capability | Backend | Needs |
| ---------- | ------- | ----- |
| Screenshots | XDG screenshot portal (grim) | a normal login session |
| Windows | `hyprctl` | nothing extra |
| Clicks, drags | its own absolute uinput pointer | `uinput` group |
| Typing, Unicode | `wtype` virtual keyboard | nothing extra |
| Key chords, scroll | `ydotoold` | `ydotool` group |
| Semantic clicks | AT-SPI | `services.gnome.at-spi2-core` |

The package wrapper suffixes `hyprctl`, `wtype`, `ydotool` and `grim` onto
`PATH`, and the MCP entry pins `YDOTOOL_SOCKET` to the NixOS daemon's socket.

Traps:

- Group changes need a fresh login. Borrowing a group with `sg` is not a
  substitute: the portal rejects screenshots from that subshell, and the
  absolute pointer, which sizes itself from a screenshot, then silently falls
  back to `ydotool`.
- With at-spi2-core disabled NixOS exports `GTK_A11Y=none` and
  `NO_AT_BRIDGE=1`, and a session started before enabling it keeps them. Apps
  launched in that session expose no accessibility tree until the next login.
- Semantic clicks read a tree cached by `get_app_state`, so call it first in
  the same MCP session.
- The absolute pointer is sized once per server process. After a monitor
  change, restart jcode (or the MCP) before clicking by coordinates.
- Chords go through `ydotool` keycodes. On qwerty-fr, `ctrl+a` and `Return`
  were verified; layout-dependent symbols in chords may map differently.

## Local patches

`overlays/custom-packages.nix` applies these patches to the flake input, in
order, through `pkgs.applyPatches` in `package.nix`:

- `no-macos-option-char-shortcuts.patch`: `JCODE_NO_MACOS_OPTION_CHAR_SHORTCUTS`
  disables the translation of macOS Option+Shift characters into Alt
  shortcuts.
- `claude-account-auth-lock.patch`: serialized `auth.json` writes for Claude
  accounts, and one usage report per account.
- `keep-swarm-workers-alive.patch`: a swarm worker's turn survives its terminal
  being closed.

### Claude account auth lock

This used to be a full account failover patch. Upstream rewrote that area
after `29d17a9`: `provider/stream_start.rs` now waits for the first transport
event so a 429 inside the stream reaches the router (the bug behind issues
#1130 and #1612), and failover between pool accounts goes through cancelable
countdown prompts. The old patch no longer applied and overlapped upstream, so
the failover half was dropped. Upstream's behaviour is now the failover
behaviour: it asks first (`[provider].cross_provider_failover = "countdown"`)
where the old patch switched unattended. Not yet tested against a real limit.

What remains is what upstream still lacks:

- Every read-modify-write of `~/.jcode/auth.json` for Claude accounts holds a
  process mutex and an `flock` on `auth.json.lock`, so an account switch can
  no longer overwrite a refresh token that another session rotated at the same
  moment. Desktop writes through the same `jcode-base` code.
- A usage report keeps one entry per account when the active marker moves, so
  `/usage` does not list the same account twice.

The patch is generated against the pinned revision (`git diff <locked rev>
HEAD`). When `scripts/update-jcode` moves the input and the patch stops
applying, the `jcode-source-patched` build fails with the rejected hunks:
rebase it, or drop it once upstream ships the same behaviour.

### Keeping swarm workers alive

A visible swarm worker is an ordinary session with a TUI client attached over a
socket. Upstream aborts the running turn and marks the session `Crashed` when
that socket closes, unless the client asked to continue on disconnect. Only the
native SSH client asks, so closing the terminal of a local worker mid turn threw
away the work its coordinator was waiting on.

This patch makes the server retain the turn when the disconnecting session is a
spawned worker, meaning its swarm member has `report_back_to_session_id` set.
Root sessions have no spawner and keep the abort behaviour. The retained turn
uses the path that already exists for SSH: the connection is detached, the turn
runs to completion, and its result is reported to the coordinator as usual.

What it changes, all in `server/client_lifecycle.rs`:

- `is_spawned_worker` reads the swarm member for the session.
- The disconnect path takes the retain branch when `continue_on_disconnect` or
  `is_spawned_worker` holds, instead of `continue_on_disconnect` alone.
- A client that reattaches to a worker and sends a prompt gets its stdin channel
  restored under the same condition, so tools that ask for input in later turns
  reach the new terminal instead of the dead one.

Behaviour after the patch:

- Close the terminal of a worker mid turn: the turn finishes and reports back.
  `jcode --resume <session-id>` attaches to the live turn.
- Close the terminal of an idle worker: unchanged, the session is saved and can
  be resumed.
- Ctrl+C and Esc still cancel, because they send an explicit cancel request
  rather than closing the socket. `swarm stop` is unaffected.
- A permission or stdin prompt raised while no terminal is attached does not
  migrate: its pending response fails closed, as in the SSH case. A worker that
  needs approval stays stuck until a terminal reattaches.
- Root sessions and coordinators are unchanged.

Three tests in `client_lifecycle_tests.rs` drive a real socket connection with a
slow provider and drop the client mid turn. A worker's turn must finish and its
spawner must receive the completion notification, whether the turn was started
by a prompt or by a soft interrupt. A root session's turn must still be
aborted. Reverting the fix makes both worker tests fail.

`server::client_lifecycle::tests::sdk_socket_configure_list_callback_and_busy_rejection`
fails with a 5 second timeout on the unpatched pinned revision as well, so this
patch does not cause it.

The patch is generated from the `fix/keep-swarm-workers-alive` branch against
the pinned revision with the other two patches applied. After `nix flake update
jcode`, rebase that branch and regenerate it; drop it once upstream ships
equivalent behaviour.

## Updating

Bumping the input to a newer upstream master is the whole procedure:

```sh
nix flake update jcode
```

There is no generated file to refresh. If upstream changes `Cargo.lock`, the
next build regenerates the graph from it.

Two things still need manual attention:

- `crate-hashes.json` pins the git dependencies. A new git dependency, or a new
  tag on an existing one, needs its hash added. crate2nix reports the missing
  entry by name; the sandbox has no network, so it cannot prefetch.
- `version` in `package.nix` only names the output. It does not have to match
  upstream's `Cargo.toml`, but it should.
