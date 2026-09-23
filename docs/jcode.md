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
| `pkgs/jcode/package.nix` | Feature and version guards, vendored deps, and the `outputOf` indirection. |
| `pkgs/jcode/dyn.nix` | The expression evaluated inside the generator. Per-crate sources, native dependencies, and compiler settings. |
| `pkgs/jcode/crate-hashes.json` | Fixed-output hashes for the two git dependencies (`agentgrep`, `mermaid-rs-renderer`). |
| `shared/nix-features.nix` | The experimental features this configuration enables, read by both `modules/base/nix.nix` and this package. |

The overlay in `overlays/custom-packages.nix` exposes the result as
`pkgs.jcode`, and `modules/agents/jcode.nix` installs it into the user profile.
The systemd user unit still starts `~/.local/bin/jcode`, so a self-dev build can
take over the daemon without a rebuild of this repository.

## How a build runs

1. `package.nix` checks the guards below, then builds a vendor directory with
   `rustPlatform.importCargoLock`, pinning the two git dependencies by hash.
2. drowse builds the generator: a content-addressed derivation named
   `jcode-0.84.0.drv` whose output is itself a derivation. Its build runs
   `crate2nix generate` over the flake input, then `nix-instantiate` over
   `dyn.nix`.
3. `dyn.nix` imports the freshly generated `Cargo.nix`, applies the crate
   overrides, and yields `workspaceMembers.jcode.build`.
4. `builtins.outputOf` turns the generator's output into a normal store path
   dependency, and `runCommand` symlinks it so the final path carries a
   readable name.

Step 2 is serial and takes roughly three minutes cold: a vendor directory of
434 crates, then crate2nix, then instantiation of about 900 derivations. It is
cached like any other derivation, so it reruns only when the jcode input or the
settings change. Steps 3 and 4 are the usual parallel crate builds.

`dyn.nix` is read as text and evaluated in the sandbox against `<nixpkgs>`, so
it cannot import anything from this repository. Settings that need to cross
that boundary (`optLevel`, `codegenUnits`, `rootFeatures`, and the output name)
are passed as a JSON file through `passAsFile`.

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

Each crate gets only `Cargo.toml`, `Cargo.lock`, and its own directory, which is
what keeps the derivations independent. Three crates read files outside their
own directory:

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

Unrelated repository content never becomes a build input, so touching it cannot
invalidate a crate derivation.

## Features

`rootFeatures` is `["pdf" "embeddings"]`. Upstream's `default` also includes
`bedrock`, which pulls in the AWS SDK stack for live Bedrock support; nothing
here uses it, so it is left out.

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

Both are set twice on purpose. `home.sessionVariables` reaches interactive
shells, and an `environment.d` file reaches the systemd user manager, which
does not read shell profiles. Running jcode from one of the agent's own
scheduled jobs inherits the latter.

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
