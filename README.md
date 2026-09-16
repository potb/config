# NixOS Configuration

Personal NixOS and nix-darwin configuration for my machines.

## Machines

| Host | System | Description |
|------|--------|-------------|
| `charon` | x86_64-linux | NixOS workstation |
| `kerberos` | aarch64-linux | NixOS on Asahi, MacBook Pro M1 Pro, see [docs/kerberos.md](docs/kerberos.md) |
| `nyx` | aarch64-darwin | macOS (Apple Silicon) |
| `new-horizons` | x86_64-linux | NixOS server, see [docs/new-horizons.md](docs/new-horizons.md) |

## Usage

### Rebuild

```bash
# NixOS (charon)
nh os switch .

# macOS (nyx)
darwin-rebuild switch --flake .#nyx    # see Setup for the first run

# server (new-horizons), from a checkout on the machine itself
sudo nixos-rebuild switch --flake .#new-horizons

# kerberos, which must build on kerberos: see docs/kerberos.md
sudo nixos-rebuild switch --flake .#kerberos
```

### Format

```bash
nix fmt
```

### Check

```bash
nix flake check
```

## Structure

```
.
├── flake.nix              # Entry point, inputs, outputs
├── hosts/                 # One directory per machine
│   └── <host>/
│       ├── configuration.nix
│       └── modules/       # Modules only this host loads
├── modules/               # Capability traits, composed per host
│   ├── base/              # Every machine, every platform
│   ├── linux/             # Every Linux machine, server or workstation
│   ├── gui/               # Has a screen and a human at it
│   ├── desktop-apps/      # Applications a human opens to get work done
│   ├── leisure/           # Applications a human opens for fun
│   ├── dev/               # Builds software
│   ├── containers/        # Runs containers
│   ├── agents/            # Runs the coding agents
│   ├── tailscale/         # Joins the tailnet
│   ├── exit-node/         # Offers itself as an exit node
│   ├── exit-node-client/  # Egress through an exit node, with fallback
│   ├── lan/               # Reachable on the LAN and not beyond
│   ├── hardened/          # Exposed to the internet
│   ├── apps/              # One directory per application
│   └── darwin/            # macOS only
├── shared/                # Cross-platform odds and ends
├── overlays/              # Package overlays
├── checks/                # Data the flake checks validate against
├── scripts/               # Helpers referenced by the checks and docs
└── docs/                  # Runbooks and the traps worth remembering
```

A trait answers "does this machine do X", never "is this machine a Y". Hosts
compose them, so `new-horizons` and `charon` visibly share `base` and `linux`
and differ only in what they additionally do:

| Host | Traits |
|------|--------|
| `charon` | base linux gui desktop-apps leisure dev containers agents lan tailscale exit-node |
| `kerberos` | base linux gui desktop-apps dev agents lan tailscale exit-node |
| `nyx` | base gui desktop-apps dev containers agents lan darwin |
| `new-horizons` | base linux hardened tailscale exit-node-client openclaw |

Every trait evaluates on its own. Those that would otherwise need a secrets
backend declare their own option with a working default instead, so `tailscale`
enables without an auth key and `hardened` keeps its firewall without demanding
a password hash. Adding a trait to a host is a one-word change, never a
prerequisite hunt.

Traits split by platform where the platforms share nothing: `gui/linux` is a
Wayland stack and `gui/darwin` is a tiling window manager, and the loader picks
between them from the host's platform. Architecture is not a trait; the handful
of packages that differ use `lib.optionals` in place.

Flake inputs should follow this flake's `nixpkgs` unless there is a reason not
to. An input that pins its own nixpkgs builds against a second package set: it
duplicates much of the closure, ignores the overlays here, and can fail on
upstream breakage that current nixpkgs has already fixed.

## Setup

After cloning, install git hooks:

```bash
lefthook install
```

### Bootstrapping a Mac

Install Determinate Nix first, because the Darwin configuration is written
against its module rather than nix-darwin's own Nix management:

```bash
curl -fsSL https://install.determinate.systems/nix | sh -s -- install --determinate
```

The flake is written with pipe operators, which are still an experimental
feature and are only enabled by the configuration this command is about to
install. Pass them through the environment for that first run, since
`darwin-rebuild` overrides the equivalent command-line flag:

```bash
sudo env NIX_CONFIG="extra-experimental-features = pipe-operators" \
  nix run nix-darwin#darwin-rebuild -- switch --flake .#nyx
```

Afterwards `nh darwin switch . -H nyx` is enough. A few files the
installers or earlier hand-written setup wrote have to be moved out of the way
the first time, because nix-darwin and Home Manager refuse to overwrite content
they do not recognise.

Determinate Nix leaves `/etc/nix/nix.custom.conf` behind with only its own
comment header. The Determinate nix-darwin module generates that same file from
`determinateNix.customSettings`, so nix-darwin stops the first activation until
the old copy has been preserved:

```bash
sudo mv /etc/nix/nix.custom.conf /etc/nix/nix.custom.conf.before-nix-darwin
```

The standalone Homebrew installer leaves `/etc/paths.d/homebrew`, which macOS
`path_helper` reads before the Nix profile path. If it stays there, tools this
flake declares can still resolve to Homebrew copies with the same name:

```bash
sudo mv /etc/paths.d/homebrew /etc/paths.d/homebrew.before-nix-darwin
```

A hand-written `~/.ssh/config` gets the same treatment once Home Manager owns
SSH client configuration. Move it aside before switching so the generated host
blocks from `modules/base/ssh-daemon.nix` and `modules/lan/ssh-lan.nix` can be
installed without clobbering local content:

```bash
mv ~/.ssh/config ~/.ssh/config.before-home-manager
```

Other Determinate installer shell files in `/etc`, such as `/etc/zshrc`,
`/etc/zshenv`, `/etc/zprofile`, and `/etc/bashrc`, do not need this treatment.
nix-darwin already knows their installer hashes and replaces them during
activation.

Secrets are read from `~/.secrets` at runtime rather than through the
configuration, so they never reach the world-readable Nix store. Copy the
ones the machine needs across:

```bash
scp ~/.secrets/gemini-api-key nyx:~/.secrets/
```

## Firmware updates (charon)

`services.fwupd.enable` covers devices published on the Linux Vendor Firmware
Service, such as the NVMe drive and peripherals:

```bash
fwupdmgr refresh
fwupdmgr get-updates
```

`hardware.cpu.intel.updateMicrocode` loads Intel CPU microcode at early boot,
ahead of whatever the BIOS shipped. On this machine that raises the revision
from `0x12b` (BIOS 1801) to `0x133`, which includes the Raptor Lake Vmin
degradation mitigation. Verify with `journalctl -k -b | grep microcode`.

The motherboard BIOS cannot be flashed from Linux. ASUS publishes only server
and workstation boards on LVFS, not consumer ROG STRIX models, and the board
exposes no UEFI capsule targets, so every entry under
`/sys/firmware/efi/esrt/entries/` has an empty `fw_class`. `fwupdmgr` will
never list the motherboard, which is expected rather than a misconfiguration.
Writing the SPI flash directly with `flashrom` is not a workaround either, as
the descriptor is locked on retail boards and forcing a write risks bricking
them. Use ASUS EZ Flash 3 from the firmware setup menu, or USB BIOS FlashBack
with the machine powered off.
