# new-horizons

Headless NixOS host for the OpenClaw assistant `hal`.

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
| `tailscale-serve`  | publishes the gateway and browser inside the tailnet    |
| `podman-neko`      | Neko, a browser a human and the agent share             |
| `neko-cdp-bridge`  | relays Neko's debugging port out of its netns           |
| `restic`           | nightly backup of agent state and browser profile       |
| `qemu-guest-agent` | lets the hypervisor report addresses and shut down well |

Nothing listens on a public port except SSH.

## Backups

`restic` takes a nightly snapshot of `/var/lib/openclaw` and
`/var/lib/neko/profile`, which covers the agent's sessions and memory and the
browser's logins. Caches and `node_modules` are excluded.

Retention keeps 7 daily, 5 weekly and 6 monthly snapshots. The unit runs
`forget --prune` after every backup, so the repository does not grow without
bound; a run that drops a snapshot logs `snapshots have been removed, running
prune` and reports what it reclaimed.

The repository sits at `/var/lib/backup/restic`, on the same disk as the data
it protects. That guards against a bad deploy, a wrong `rm`, or an agent
mistake, and not against losing the disk or the provider. Anything that would
hurt to lose should also live somewhere else; the persona files already do,
since they come from this repository.

A backup is only real once it restores, so check it rather than trusting the
timer:

```
sudo restic-openclaw snapshots --compact

sudo restic-openclaw restore latest --target /tmp/restore-check \
  --include /var/lib/openclaw/workspace/MEMORY.md

sudo cmp /tmp/restore-check/var/lib/openclaw/workspace/MEMORY.md \
  /var/lib/openclaw/workspace/MEMORY.md
```

The NixOS module generates that `restic-openclaw` wrapper with the repository
and password already set; plain `restic` is not on `PATH` and would need both
passed by hand.

## Discord

Three channels under a `hal` category:

| Channel   | Type  | Purpose                                                |
| --------- | ----- | ------------------------------------------------------ |
| `#hal`    | text  | ordinary conversation                                  |
| `#work`   | forum | one thread per topic, created by posting to the parent |
| `#notify` | text  | the only place the agent notifies                      |

Mute the first two and leave notifications on for `#notify`; the workspace
rules tell the agent to keep anything that can wait out of it.

The guild allowlist names those three channels, and DMs are restricted to the
operator.

The bot's invite granted `ADMINISTRATOR` in the guild, so the token in
`openclaw-env` can ban members, delete channels and edit roles, not merely
post in those three channels. The allowlist constrains what the agent chooses
to do, not what the credential permits. If the token ever leaks, rotate it in
the Discord developer portal and `sops secrets/new-horizons.yaml`.

Re-inviting with only what the agent uses is a kick and a fresh invite, no
config change:

```
https://discord.com/oauth2/authorize?client_id=1547996770380943360&scope=bot%20applications.commands&permissions=2252194951064640
```

That covers viewing channels, sending messages, creating and managing threads
for the forum, reading history, reactions, attachments, embeds, external emoji,
and deleting and pinning messages, which the Discord plugin exposes as tools.
It grants nothing that can ban, kick, or edit the guild, its channels, its
roles or its webhooks.

## Access from the tailnet

| URL                                           | What                |
| --------------------------------------------- | ------------------- |
| `https://new-horizons.taile99a6c.ts.net`      | OpenClaw Control UI |
| `https://new-horizons.taile99a6c.ts.net:8443` | Neko browser        |

Both are Serve, not Funnel, so they exist only inside the tailnet. Port 22 is
the only thing answering on the public address.

The Control UI opens from any tailnet device without a token, because Serve
authenticates it with tailnet identity headers. The HTTP API is separate and
still demands the token, which is `OPENCLAW_GATEWAY_TOKEN` in `openclaw-env`:
requests to `/api/*` answer `401` without it even from inside the tailnet.

The Neko URL needs the `:8443` and the `https://`; nothing listens on 8080 or
80 from the tailnet. Media rides a single TCP port, 52100, also published
through Serve, so watching the session from a phone needs no UDP.

The login screen asks for a username and a password, but only the password
carries meaning: it selects the role. Neko runs in multiuser mode, so there
are no accounts, and the username is just the display name in the session
list. Both passwords live in `neko-env`:

| Secret                                 | Role              |
| -------------------------------------- | ----------------- |
| `NEKO_MEMBER_MULTIUSER_ADMIN_PASSWORD` | watch and control |
| `NEKO_MEMBER_MULTIUSER_USER_PASSWORD`  | watch only        |

Watching starts immediately, but typing and clicking do not: the mouse and
keyboard icons start greyed out and control has to be requested from the
toolbar before input reaches the browser. Until then keystrokes are accepted
and silently discarded, which looks like a broken stream rather than a
permission state.

The agent and any human share one screen and one input focus, so taking
control while the agent is mid-task means fighting over the same cursor. The
viewer password avoids that.

From a phone, in order:

1. Confirm the device is on this tailnet and not a work one, since the address
   only resolves there.
2. Open `https://new-horizons.taile99a6c.ts.net:8443`, including the port.
3. Type any display name, then the password for the role you want.
4. Tap the keyboard or mouse icon to request control before expecting to type.

Each of those steps has its own failure that looks like something else: the
wrong tailnet gives a name that does not resolve, a missing port gives nothing
listening, an empty display name gives a login error rather than a hint, and
skipping the control request gives a picture that ignores the keyboard.

The remote route is worth knowing when it misbehaves, because a browser
running on the server never uses it. Neko offers exactly one candidate to a
client that is not local, the tailnet address on TCP 52100, so media travels
phone to Serve to container with no loopback fallback to mask a problem:

```
tailscale status | grep new-horizons
curl -o /dev/null -w '%{http_code}\n' https://new-horizons.taile99a6c.ts.net:8443/
```

If the page loads but the picture never appears, the media port is the link to
suspect rather than the UI. The browser's own statistics name the pair in use,
which settles whether traffic really crossed the tailnet:

```
(await (await window.__pcs?.[0]?.getStats?.())?.values?.())
```

A healthy remote session shows a succeeded pair whose remote candidate is
`100.125.71.113:52100/tcp host` with a growing `bytesReceived`.

### The agent asks for the keyboard

Taking over is not only a way to watch. The agent treats it as its way out of
a dead end: a 2FA code it cannot read, a CAPTCHA, an expired login, a page that
behaves differently from the DOM it sees. Rather than inventing a workaround or
abandoning the task, it names what blocks it, the tab, and the action it needs,
and it waits without touching the browser until told the step is done.

The request arrives wherever the conversation already is, or in `#notify` when
the task stalls and nobody is talking to it. Control still has to be requested
from Neko's toolbar; the agent cannot hand it over on its own.

This lives in the workspace files, not in the gateway config. `AGENTS.md` says
when to ask and what the request must contain, `TOOLS.md` describes the shared
session. Changing either is an edit to the sops secret and a deploy.

## Secrets

sops-nix, decrypting with the host's own SSH key converted to age. The
workspace bootstrap files are encrypted the same way and are bind-mounted into
the workspace from `/run/secrets`, so the agent's instructions appear neither
in this public repository nor in the world-readable Nix store. Outside the
service's mount namespace those paths are empty placeholder files.

Editing from a new machine needs only this repository and the passphrase:

```
./scripts/sops-unlock
sops secrets/new-horizons.yaml
```

## Rebuilding on new hardware

The host decrypts with its own SSH key, so a replacement machine has a
different key and cannot read the existing secrets. Give it access rather
than re-generating the secrets:

```
ssh-keyscan <new-address> | grep ed25519 | cut -d' ' -f2-3 | ssh-to-age
```

Put that public key in `.sops.yaml` under the host anchor, then re-encrypt to
the new recipient list and commit:

```
./scripts/sops-unlock
sops updatekeys secrets/new-horizons.yaml
sops updatekeys secrets/workspace/*.md
```

Everything else follows from this repository, so recovery needs the
passphrase and nothing from the old machine. The agent's own state, its
sessions and memory, lives only in the backups.

## Deploying a change

```
ssh potb@185.163.119.202
cd /tmp/cfg && git pull
sudo nixos-rebuild switch --flake .#new-horizons
```

`nix flake check` validates the generated OpenClaw config against the gateway's
own JSON schema, which catches unknown keys, missing required keys and bad enum
values before they reach the server. The schema is committed at
`checks/openclaw-config-schema.json.gz` so the check also runs on macOS, where
the Linux gateway cannot be built; on Linux a second check fails if that copy
has drifted. Refresh it with `./scripts/update-openclaw-schema.sh` after
bumping the gateway.

## Things that cost time once

Before reaching for a fix, note what already recovers without help. These were
checked by killing the real processes on the running host:

| Broken                  | What happens                                                                                             |
| ----------------------- | -------------------------------------------------------------------------------------------------------- |
| Chromium killed         | supervisord restarts it, the debugging port returns, the agent's browser tool works again                |
| `podman-neko` restarted | `neko-cdp-bridge` follows the new network namespace, because it is bound to the container unit           |
| Host rebooted           | every unit comes back and the browser keeps its logins, though a stale profile lock used to prevent this |
| Secrets re-installed    | the gateway restarts when what it reads no longer matches the installed secret                           |

What does not self-heal is anything needing a decision: a changed upstream
schema, an expired token, or a revoked key.

Disk pressure is handled: `nix-gc` runs nightly with `--delete-older-than 7d`
and reclaimed 14.5 GiB on its last run. The store dominates usage, so if space
ever gets tight, look there before the agent's state, which is a few hundred
megabytes.

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
- Neko's image also ships a Chromium enterprise policy with
  `DeveloperToolsAvailability: 2`, which makes the browser answer every
  `Target.attachToTarget` with `Not allowed`. Nothing else looks wrong:
  `/json/list` still lists pages and per-page sockets still upgrade, but
  Playwright sees zero pages and the agent reports `No pages available in the
connected browser`. We mount our own policy file instead. To tell this apart
  from a transport problem, attach by hand rather than trusting the target list:

  ```
  curl -s http://127.0.0.1:9222/json/list | jq -r '.[0].type'
  ```

  A populated list with a failing attach means policy, not networking.

- Neko defaults to advertising `127.0.0.1` for WebRTC. The stream then plays
  only on the server itself and every remote client shows a black screen, so
  the tailnet address is written into an environment file at boot. Verify with
  the ICE candidate rather than the page load: it must carry the tailnet IP.
- Published container ports bypass the NixOS firewall, because podman DNATs in
  `ip nat` prerouting ahead of the `nixos-fw` input chain. Binding a port to
  `0.0.0.0` in `virtualisation.oci-containers` therefore exposes it publicly
  even with `allowedTCPPorts = []`. Bind to `127.0.0.1` and let Serve publish it.
- Chromium records the hostname it started on in the singleton lock inside its
  profile, and podman hands the container a fresh random hostname on every run.
  After a reboot Chromium then refuses to start with "The profile appears to be
  in use by another Chromium process on another computer" and never opens its
  debugging port, while Neko keeps serving the desktop, so the only symptom is
  the agent losing the browser. The container hostname is pinned and a stale
  lock is cleared before start. After any reboot, confirm the browser came back
  rather than only checking that the units are active:

  ```
  sudo podman exec neko supervisorctl status chromium
  curl -s http://127.0.0.1:9222/json/version | jq -r .Browser
  ```

- sops-nix installs secrets into a fresh `/run/secrets.d/<n>` on every
  activation and moves the `/run/secrets` symlink, but bind mounts inside a
  running service stay pinned to the generation that existed when it started.
  Once the old generation is removed those mounts point at deleted inodes,
  which still read the stale text, so an edited `SOUL.md` would never reach the
  agent while `ls` and every unit still looked correct. `restartUnits` does not
  cover this, because it fires on content change and the staleness comes from
  the generation roll. An activation snippet compares what the service reads
  against the installed secret and restarts it on mismatch. It runs before the
  units are restarted, where `PATH` holds no `systemctl`, so it calls one by
  absolute store path: a bare `systemctl` fails with `command not found`, and
  because the script keeps going the guard silently never runs. To check by
  hand:

  ```
  pid=$(systemctl show -p MainPID --value openclaw-gateway)
  sudo nsenter -t "$pid" -m -- cmp \
    /var/lib/openclaw/workspace/SOUL.md /run/secrets/workspace/SOUL.md
  ```

- Activation snippets all run inside one shared shell script, so calling `exit`
  in a snippet ends the whole activation. The remaining steps, including
  repointing `/run/current-system`, are skipped while
  `switch-to-configuration` still exits zero and prints its usual success line.
  Guard with a conditional rather than an early `exit`.
- OpenClaw validates workspace context files with `lstat` and rejects anything
  that is a symlink or has more than one hard link. sops-nix creates symlinks
  when given a `path`, so the persona files were silently reported as
  `missing` and never reached the system prompt, while still looking correct
  in `ls`. They are bind-mounted over placeholder files instead. Check the
  agent's own view rather than the directory listing:

  ```
  sudo nsenter -t $(systemctl show -p MainPID --value openclaw-gateway) -m -- \
    stat -c '%n %F nlink=%h size=%s' /var/lib/openclaw/workspace/SOUL.md
  ```

  A non-zero size and a regular file is what matters. The link count reads `0`
  rather than `1` once a later activation has replaced the secrets generation
  the mount points at, which is harmless: the requirement is at most one link,
  and the content is still the installed secret.

- Memory search defaults to OpenAI embeddings. With only an OpenRouter key the
  index cannot be built and recall stays paused, which the agent reports as
  its memory being unavailable. `models.providers.<id>.api` must be
  `openai-completions` for an OpenAI-compatible endpoint: `openai-compatible`
  looks plausible, appears in prose in the upstream memory documentation, and
  is not in the schema. An invalid `models` block makes the gateway drop its
  bundled plugins rather than fail loudly, so the first visible symptom is
  unrelated commands disappearing.
- The CLI reads `~/.openclaw` unless `OPENCLAW_CONFIG_PATH` is set. Running
  `openclaw memory status` without it reports on a config the service does not
  use, which looks exactly like a broken deployment.
