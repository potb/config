# Host output audit

`nix/audit.nix` builds one check per host, `checks.<system>.audit-<host>`, from
the host's `system.build.toplevel` and reports every finding in one run before
failing. The file checks (1 to 4 below) walk the toplevel's own files; only the
closure check (5) reaches every package the host ships.

## What it checks

1. Dangling symlinks.
2. Build-environment paths inside any file, text or binary: `/build/`,
   `/nix/var/nix/builds/`, `/tmp/nix-build-` and `/homeless-shelter`.
3. ELF hygiene: the interpreter lives in `/nix/store`, and every RPATH entry is
   a store path or starts with `$ORIGIN`.
4. Secrets, through `gitleaks dir`, skipping files over 50 MB.
5. The runtime closure: total size under a limit (1024 MiB by default) and no
   build tools (full gcc, clang, binutils, cmake, stdenv). The `dev`, `doc`,
   `man`, `devdoc` and `info` outputs do not count towards it.

Checks 1 to 4 look at the files of the toplevel itself, which for a system are
mostly symlinks into the rest of the store. They do not descend into every
package of the closure; check 5 is the one that covers the whole closure.

## Where the hosts are wired in

`hostAudits` in `flake.nix` picks the hosts whose platform matches the check's
system, so each host is audited on its own system only. `offhostModules` holds
modules a host needs to build away from its own hardware. kerberos gets the
same stub peripheral firmware as `kerberos-offhost`, since the real firmware
can only be extracted on the machine.

## Overrides

Per-host settings live in `auditOverrides` in `flake.nix`. The keys are those of
`defaults` in `nix/audit.nix`: `forbiddenPatterns`, `forbiddenClosureRefs`,
`maxClosureMB`, `secretsMaxFileMB`, `symlinks`, `elf` and `secrets`. Evaluation
stops on any other key, so a typo cannot silently leave a default in place.

### Toolchain refs on every host

All three hosts load the `dev` trait, and `modules/dev/tools.nix` installs
clang, gcc and binutils on purpose. A compiler in a workstation's closure is
the point of that trait, so for these hosts `forbiddenClosureRefs` drops the
gcc, clang and binutils patterns and keeps cmake and stdenv, which nothing
installs deliberately. If a host stops loading `dev`, drop its override.

On nyx the audit found `clang-21.1.8` this way. The first path it reaches it
through is not `modules/dev/tools.nix` but nix-homebrew's patched brew, which
pins nixpkgs' ruby, whose `rbconfig.rb` records the compiler used to build it so
that native gems can compile later. clang is in the closure either way.

### nyx closure size

nyx's runtime closure was 10277 MiB across 1611 store paths on 2026-11-02. The
1024 MiB default is sized for a package, not a whole workstation, so nyx gets
12288 MiB: about 20% headroom, enough to catch a sudden jump without failing on
ordinary drift. Raise it when the growth is understood, not to make it pass.

## Running it

```bash
nix flake check -L
nix build -L .#checks.aarch64-linux.audit-kerberos
```

`nix flake check` only builds the current system's checks. aarch64-linux builds
on the linux builder from nyx; x86_64-linux has no builder there, so charon's
audit has to run on charon.

## CVE report

`nix build .#cve-nyx` scans nyx's runtime closure with grype. It is an
aarch64-darwin package, not a check, and it never fails on findings: CVE
matches on nixpkgs are noisy, so it reports instead of gating. It does fail if
the database cannot be fetched or imported, for example when a nixpkgs bump
brings a grype that wants a newer database schema.

The build is pure. `nix/grype-db.json` pins one grype database release by its
path and sha256, `nix/cve.nix` fetches it as a fixed-output derivation, and
grype itself comes from the locked nixpkgs. The pin is a committed file, not a
flake input, so `nix flake update` leaves it alone and any checkout can refetch
the same tarball for as long as Anchore keeps it. To move it forward:

```bash
nix run .#cve-update-db
nix build .#cve-nyx
cat result/summary.txt
```

`cve-update-db` writes the newest release from Anchore's `latest.json` into
`nix/grype-db.json`; commit the change like any other bump. The report is
exactly as fresh as that file.

`result/` holds `summary.txt` (counts, every open critical and high match, and
the matches a nixpkgs patch covers), `report.txt` (grype's table),
`grype.json`, the SBOM `bom.cdx.json`, `patches.json` and a link to the
database tarball, which keeps it from being garbage-collected while `result`
exists.

The SBOM is built in two halves. At evaluation, `nix/cve.nix` walks the
dependency attributes of the host's system packages, fonts, Nix itself and
every home-manager user's packages, and records each output path with its
pname, version, `meta.identifiers.cpe` and patch names. In the build,
`nix/cve-sbom.py` keeps only the paths in the realised runtime closure, from
`closureInfo`, and names the paths the walk did not reach from their store
path. Configuration files such as `etc-*.conf` are skipped. grype runs with
`--add-cpes-if-none`, which guesses a CPE for every component nixpkgs gives
none.

A match counts as patched when one of the package's nixpkgs patches carries
the CVE id in its file name, the convention nixpkgs uses for backported
security fixes. Those matches are listed separately and left out of the open
counts.

Read the result as triage, not as a verdict. A backport whose patch file is not
named after the CVE still shows as open, guessed CPEs collide with unrelated
products of the same name, and packages with no usable version are skipped, so
a short report does not mean a safe system.

Adding another host is one line in `flake.nix`, next to `cve-nyx`:
`(import ./nix/cve.nix {inherit pkgs;}).forHost "<host>" self.<nixos|darwin>Configurations.<host>`
under that host's system.

### Other CVE scanners

vulnxscan, from sbomnix, needs the Nix daemon and network access, so it cannot
run in the sandbox. It still works as a manual, online second opinion:
`nix run github:tiiuae/sbomnix#vulnxscan -- /run/current-system`.
