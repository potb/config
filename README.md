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
darwin-rebuild switch --flake .#nyx
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
