# NixOS Configuration

Personal NixOS and nix-darwin configuration for my machines.

## Machines

| Host | System | Description |
|------|--------|-------------|
| `charon` | x86_64-linux | NixOS desktop |
| `nyx` | aarch64-darwin | macOS (Apple Silicon) |

## Usage

### Rebuild

```bash
# NixOS (charon)
nh os switch .

# macOS (nyx)
darwin-rebuild switch --flake .#nyx    # see Setup for the first run
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
├── nixos/                 # NixOS system configuration
│   ├── configuration.nix  # System entry
│   └── modules/           # System modules
├── darwin/                # macOS configuration
│   ├── configuration.nix  # Darwin entry
│   └── modules/           # Darwin modules
├── home-manager/          # User configuration
│   ├── home.nix           # Home entry
│   └── modules/           # User modules
├── shared/                # Cross-platform
│   ├── fonts.nix
│   ├── zed.nix
│   └── modules/theme.nix
└── overlays/              # Custom package overlays
```

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
blocks from `modules/ssh.nix` can be installed without clobbering local content:

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
