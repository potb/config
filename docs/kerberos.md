# kerberos

A 16-inch MacBook Pro (M1 Pro, 2021) running NixOS on Asahi Linux, triple
booting alongside macOS and Fedora Asahi Remix.

## Hardware

| | |
|---|---|
| CPU | Apple M1 Pro, 10 cores (8 performance, 2 efficiency) |
| Memory | 15 GiB |
| Root | `/dev/nvme0n1p10`, ext4, 342.8G, UUID `b939a6f5-97f7-4358-8856-3fe2f2e26175` |
| ESP | `/dev/nvme0n1p4`, vfat, 477M, UUID `42DE-1DF2`, labelled `EFI - NIXOS` |

There is no disko module and there should not be one. This disk holds four APFS
containers belonging to macOS and to the two Linux bootloader stubs, and a
declarative partitioner pointed at it would be pointed at the machine's ability
to boot at all.

## Kernel

The Asahi kernel comes from `nixos-apple-silicon`, pinned to a revision rather
than tracking a branch. Upstream has no working binary cache, which they state
in their own `docs/binary-cache.md`, and nixpkgs carries no `linuxPackages_asahi`,
so every kernel change means building from source: roughly an hour on this
machine's ten cores. Pinning means that cost is paid when the pin is bumped and
at no other time.

Bumping the pin is therefore a deliberate act. Plan for the build, and keep the
previous generation in the boot menu until the new kernel has booted twice.

### Fetching the source

GitHub rate-limits the kernel tarball aggressively, and `codeload.github.com`
ignores authentication tokens, so a personal access token does not help. When
`nix build` fails with HTTP 429 on `AsahiLinux/linux`, fetch the source from
another machine and copy it across:

```
git clone --depth 1 --branch asahi-<version> --single-branch \
  https://github.com/AsahiLinux/linux.git /tmp/asahi-src
rm -rf /tmp/asahi-src/.git
nix store add-path /tmp/asahi-src --name source
nix-store --export /nix/store/<hash>-source | ssh kerberos nix-store --import
```

The store path is content-addressed, so if the resulting hash matches what the
derivation asks for, the source is exactly what the build expects and nothing
about the verification has been weakened.

## Peripheral firmware

Wi-Fi, the webcam and the ambient light sensor need non-free firmware that the
Asahi Installer extracts from macOS onto the ESP. Pure flake evaluation cannot
read `/boot`, so `hardware.asahi.peripheralFirmwareDirectory` cannot use the
upstream default, which probes the filesystem. Instead the host fetches
`file:///boot/vendorfw/firmware.cpio` by hash, which evaluates purely and is
checked at build time.

The consequence is that **this host evaluates only on this host**. Anywhere else
the fetch fails with "Could not open file /boot/vendorfw/firmware.cpio", so
`nix build .#nixosConfigurations.kerberos...` has to run on kerberos. The other
three hosts are unaffected and still evaluate from anywhere.

This also constrains CI. `nix flake check` evaluates every attribute under
`nixosConfigurations`, kerberos included, so running it on a machine without the
firmware fails on the missing file. The workflow therefore builds the checks by
name rather than calling `nix flake check`, and the build matrix covers charon,
new-horizons and nyx. kerberos is checked on kerberos, where
`nix flake check` works normally. `scripts/flake-check`, which the pre-commit
hook runs, does the same thing locally.

Only the firmware path is unevaluable, though, and that is a smaller hole than
it first appears. The `kerberos-offhost` check substitutes an empty stub for
`hardware.asahi.peripheralFirmwareDirectory` through `extendModules` and
evaluates everything else: the full system derivation, every assertion and
warning, and whether any package in the closure lacks an aarch64-linux build.
So a change that breaks kerberos is caught from any machine, and only a change
to the firmware itself needs the real hardware.

The check records the derivation path rather than depending on it. Depending on
it would give the output string context, and realising a check would then build
an entire aarch64 system on whatever machine ran it.

Two approaches that look like fixes are not. A fixed-output derivation copying
from `/boot` fails because the build sandbox cannot see the path either.
Guarding with `builtins.pathExists /boot/vendorfw/firmware.cpio` is worse: under
pure evaluation, which is what flakes use, it returns false even on kerberos
where the file plainly exists, so the guard would silently disable firmware on
the one machine that needs it. It returns true only under `--impure`, which is
what makes the trap convincing when tested by hand.

If the firmware is ever refreshed, from macOS via `curl https://alx.sh | sh`
and "Rebuild vendor firmware package", the recorded hash in
`hosts/kerberos/modules/hardware.nix` must be updated to match.

## Exit node

This laptop advertises itself as an exit node, as a fallback behind `charon`
for `new-horizons`. It is picked only while charon is unreachable, which for a
machine that travels and sleeps means the VPS's egress can land on whatever
network this laptop is on at the time. Suspending it is not a problem: the
selector on new-horizons drops an offline node within 30 seconds.

The route needs approving once in the admin console. Until then the host
advertises an exit node that no client may use, and it looks offline to the
selector rather than unapproved.

## Boot order

Three operating systems share this disk, and two separate mechanisms decide
what boots. Both have to agree, and diagnosing the wrong one wastes time.

**Apple's boot picker** chooses which Asahi stub to start, and `asahi-bless`
reads and sets it:

```
sudo asahi-bless --list-volumes
sudo asahi-bless --set-boot NixOS
```

**U-Boot's EFI boot manager** then chooses what to run within that stub, and
this is the one that produced a GRUB prompt on every boot here. Its variables
persist in `/boot/ubootefi.var` on the NixOS ESP, and it had an explicit
`Boot0003 = Fedora -> \EFI\fedora\shimaa64.efi` entry ordered ahead of the
automatic device scans that find systemd-boot. `asahi-bless` correctly reported
NixOS as the active volume the entire time, because it describes the other
mechanism entirely.

`/sys/firmware/efi/efivars` is read-only here, since U-Boot implements no EFI
variable runtime services. This is also why `boot.loader.efi.canTouchEfiVariables`
must be false, which upstream's module forces anyway. Changing the boot order
means editing `/boot/ubootefi.var` directly.

The file format is a small header followed by the variable store:

| offset | field |
|---|---|
| 0 | 8 reserved bytes |
| 8 | magic, `UbEfiVa\x01` |
| 16 | `u32` length, equal to the file size |
| 20 | `u32` CRC32 over the bytes from offset 24 to length |
| 24 | variables, each a UTF-16LE name followed by its value |

The CRC must be recomputed after any edit. U-Boot rejects a file that fails the
check, and a rejected store means losing every boot entry it holds, so keep a
copy of the original first. `/boot/ubootefi.var.orig` is the copy taken before
the reordering described above.
