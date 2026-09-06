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

Afterwards the usual `darwin-rebuild switch --flake .#nyx` is enough.

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
