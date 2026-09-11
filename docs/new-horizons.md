# new-horizons

Headless NixOS host for the OpenClaw assistant `hal`.

The name follows the convention in this repository: servers take the names of
probes that targeted Pluto, personal machines take Pluto's moons, and agents
take the names of fictional AIs.

## The machine

netcup KVM guest, 4 vCPU, 7 GB RAM, one 160 GB virtio disk, **legacy BIOS**.
Public IP 185.163.119.202, tailnet address 100.125.71.113.

Partitions, laid out by disko:

| Partition | Label      | Purpose                     |
| --------- | ---------- | --------------------------- |
| vda1      | `biosboot` | 1 MiB BIOS boot (GRUB core) |
| vda2      | `swap`     | 4 GiB                       |
| vda3      | `nixos`    | rest, ext4, mounted at `/`  |

BIOS rather than UEFI is why this host takes GRUB while charon takes
systemd-boot.

## Access

`potb` over SSH with the nyx key. Root login and password authentication are
both disabled; fail2ban watches the public port with the tailnet exempted.

The account password lives in sops as a yescrypt hash and is applied through
`hashedPasswordFile`, with `users.mutableUsers = false` so the hash is
authoritative. Wheel escalates without a prompt, which matters because a
key-only login has no password to type at a sudo prompt.

If both the key and the tailnet are ever unavailable, the netcup VNC console is
the way back in.

## Services

| Service            | What it does                                            |
| ------------------ | ------------------------------------------------------- |
| `openclaw-gateway` | the agent, loopback on 18789                            |
| `tailscaled`       | tailnet membership                                      |
| `tailscale-serve`  | publishes the gateway and browser inside the tailnet     |
| `podman-neko`      | Neko, a browser a human and the agent share             |
| `neko-cdp-bridge`  | relays Neko's debugging port out of its netns           |
| `restic`           | nightly backup of agent state and browser profile       |
| `qemu-guest-agent` | lets the hypervisor report addresses and shut down well |

Nothing listens on a public port except SSH.

## Discord

Three channels under a `hal` category:

| Channel   | Type  | Purpose                                              |
| --------- | ----- | ---------------------------------------------------- |
| `#hal`    | text  | ordinary conversation                                |
| `#work`   | forum | one thread per topic, created by posting to the parent |
| `#notify` | text  | the only place the agent notifies                    |

Mute the first two and leave notifications on for `#notify`; the workspace
rules tell the agent to keep anything that can wait out of it.

The guild allowlist names those three channels, and DMs are restricted to the
operator.

## Access from the tailnet

| URL                                             | What              |
| ----------------------------------------------- | ----------------- |
| `https://new-horizons.taile99a6c.ts.net`        | OpenClaw Control UI |
| `https://new-horizons.taile99a6c.ts.net:8443`   | Neko browser      |

Both are Serve, not Funnel, so they exist only inside the tailnet. Port 22 is
the only thing answering on the public address.

## Secrets

sops-nix, decrypting with the host's own SSH key converted to age. The
workspace bootstrap files are encrypted the same way and are written straight
into the workspace, so the agent's instructions appear neither in this public
repository nor in the world-readable Nix store.

Editing from a new machine needs only this repository and the passphrase:

```
./scripts/sops-unlock
sops secrets/new-horizons.yaml
```

## Deploying a change

```
ssh potb@185.163.119.202
cd /tmp/cfg && git pull
sudo nixos-rebuild switch --flake .#new-horizons
```

`nix flake check` validates the generated OpenClaw config against the schema the
packaged gateway prints, which catches unknown keys, missing required keys and
bad enum values before they become a crash loop on the server.

## Things that cost time once

- The VM prefers its virtual DVD over the disk. After an install, detach the
  ISO in the netcup panel, and note that a boot-order change needs a power
  cycle rather than a reboot.
- The installer image runs entirely in RAM. Without swap enabled, evaluating
  this configuration gets the builder OOM-killed, so enable the swap partition
  and point `TMPDIR` at the target disk before building.
- `services.tailscale.authKeyParameters` appends a query string to the key and
  the unit interpolates the file's contents directly, so setting any parameter
  turns a valid key into one the control plane rejects.
- Chromium binds its debugging port to loopback inside the container whatever
  `--remote-debugging-address` says, hence the bridge.
- Neko's image hardcodes its Chromium command in supervisord, so
  `NEKO_CHROME_FLAGS` is ignored and the unit file has to be replaced.
