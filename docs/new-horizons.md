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
| `tailscale-exit-node` | picks the exit node egress leaves through, or none   |
| `exit-node-bypass-rule` | keeps replies to inbound traffic off the exit node |
| `tailscale-serve`  | publishes the gateway and browser inside the tailnet    |
| `podman-neko`      | Neko, a browser a human and the agent share             |
| `neko-cdp-bridge`  | relays Neko's debugging port out of its netns           |
| `restic`           | nightly backup of agent state and browser profile       |
| `motis`            | public transport router, loopback on 8090               |
| `motis-import`     | rebuilds the router's data when the regions in use change |
| `owntracks-receiver` | stores the phone's position, loopback on 8765          |
| `qemu-guest-agent` | lets the hypervisor report addresses and shut down well |

Nothing listens on a public port except SSH.

## Public transport

The agent answers transit questions through `transit`, a command on its `PATH`
that returns JSON. It asks the local MOTIS router when the trip lies in a region
loaded on this host, and Transitous, the volunteer-run MOTIS for all of Europe,
otherwise. Trip and stop identifiers are the same on both, because the local
import names its datasets exactly as Transitous does, so a trip found on one
can be followed on the other.

Why run a router at all when Transitous exists: a query to Transitous carries
the exact start and end coordinates, and Transitous keeps request logs, with
the URL and the IP address, for two days. Local routing keeps the places the
user comes and goes from on this machine. Transitous also lacks live data for
some networks that publish it; the local import takes the producers' live
feeds directly.

### Regions on demand

MOTIS reads one OpenStreetMap file and cannot add a region while it runs, so
"on demand" is rebuild and swap. `motis-import` works out the regions wanted,
and when that set differs from what is loaded, builds a new import next to the
running one and moves the `current` link. The router keeps answering from the
old data until the new one is complete, then restarts onto it.

A region is wanted when it is pinned, or when a file named after it exists in
`/var/lib/motis/requests`. `transit plan` writes that file for every region a
trip touches, and `transit regions --request <region>` writes it on purpose.
A path unit starts `motis-import` as soon as the directory changes, and a daily
timer rebuilds anyway to keep timetables current. Requests expire after 14
days without use, and at most 3 regions are loaded, pinned ones included; past
that cap the most recently requested win. The cap is memory, measured on this
host: three regions, one of them Île-de-France, import in about 7 minutes at a
3 GB peak and serve at 1.6 GB, inside the router's 2 GB limit, next to a
gateway at about 1 GB. A fourth needs a new measurement first.

The pinned regions are the ones the user lives and travels in, which says more
about them than this public repository should. They live in
`secrets/transit.yaml` under `pinned-regions`, as Geofabrik region ids
separated by spaces:

```
./scripts/sops-unlock
sops secrets/transit.yaml
```

Regions are Geofabrik's French extracts, which still follow the regions that
existed before 2016; `regions.py` maps each to its départements by hand, and
that map cannot drift. Feeds come from the Transitous catalogue for France,
which already picks the best source per network, SNCF as NeTEx with SIRI live
data for instance. Each feed is placed on the map through the area its dataset
declares on transport.data.gouv.fr, resolved to départements through
geo.api.gouv.fr. Timetables are downloaded from the Transitous mirror, which
serves them cleaned and deduplicated, with the producer's own URL as a
fallback. A build where more than half of the timetables are unavailable is
abandoned and the running import stays.

Measured with two of the largest French regions loaded: the import takes about
a minute and peaks at 3.7 GB inside its 4 GB cap, the data is 1.4 GB, and the
router serves in about 1 GB with live data applied.

```
motis-regions status
transit regions --at "Lyon Part-Dieu"
journalctl -u motis-import -n 50
systemctl status motis
```

### The agent's instructions

The `transit` skill tells the agent how to read the output: say whether a time
is live or scheduled, check what the geocoder understood, read the alerts, and
watch planned trips without repeating an alert it already sent. Like the other
workspace files, it describes the assistant and so is encrypted, at
`secrets/workspace/skills/transit/SKILL.md`, and bind-mounted into the
workspace.

## The user's position

The phone reports its position with OwnTracks in HTTP mode to
`owntracks-receiver`, which listens on loopback 8765 and is published by Serve
on `https://new-horizons.taile99a6c.ts.net:8444/pub`, tailnet only. A request
needs both the Basic credentials, `owntracks` and `owntracks-password` from
`secrets/new-horizons.yaml`, and a `Tailscale-User-Login` of the owner. Serve
sets that header from the connecting device and overwrites whatever a client
sends, and the receiver refuses requests without it, so a caller on this host
that bypasses Serve is refused even with the password.

Positions land in `/var/lib/owntracks`: `history.jsonl`, `latest.json`, and
`transitions.jsonl` for region entries and exits. The directory belongs to the
`owntracks` user and is readable by its group, which the gateway joins. A daily
timer drops anything older than 30 days. The nightly backup leaves the
directory out on purpose: its six monthly snapshots would otherwise keep half a
year of movements that the retention is meant to forget. The agent reads it through `loc`
(`latest`, `history`, `transitions`, `coord`), and `transit plan ici …` starts
from the latest position, refusing one older than 30 minutes.

iOS decides when the app runs. OwnTracks in significant-change mode reports
roughly every 500 m or every few minutes of movement and stays quiet while the
phone does not move, so an old position usually means the user is still there.
Nothing on this side can ask the phone for a fresh fix; the reportLocation
command exists only as a reply to a report the phone sends.

Setting up a phone is a configuration file: `.otrc` JSON with `mode: 3` (HTTP),
the URL above, `auth: true`, the credentials, `deviceId`, `tid`,
`monitoring: 1`. Opening it on the phone imports it, as does the link form
`owntracks:///config?inline=<base64 of the file>`. The file holds the password,
so it is generated on demand and never committed. The phone must be on this
tailnet with location access set to Always.

```
sudo tail -1 /var/lib/owntracks/history.jsonl | jq .
loc latest
```

## Egress through home

Outbound traffic leaves through an exit node at home rather than the netcup
address: `charon` first, `kerberos` when charon is unavailable, and no exit
node at all when neither is. Websites therefore see the home IP, which is the
point: a datacentre IP is treated as a bot by a fair number of sites the agent
and the shared browser have to use.

`tailscale-exit-node` runs every 30 seconds and decides in that order. It
trusts nothing but a working request: a peer counts only when tailscaled
reports it online and advertising an exit node, and the selection stands only
once an HTTPS fetch through it succeeds. A host that advertises an exit node
but drops traffic is skipped like an offline one.

When no candidate works the unit clears the exit node instead of leaving it
set. That is deliberate and it is the opposite of Tailscale's own behaviour:
`--exit-node=auto:any` and MDM-forced exit nodes both fail closed, keeping a
dead default route and taking the host off the internet with it. Here the
agent stays reachable and keeps working from the netcup IP, and the worst case
is a visible change of address rather than an outage.

The cost of that choice: egress silently moves between three addresses, so a
service that pins a session to an IP may log the agent out mid-task, and home
bandwidth carries the browser's traffic while an exit node is selected.

IPv6 is part of that cost. This netcup guest has no native IPv6 route, so the
only IPv6 egress it has is the exit node's, and clearing the exit node takes
IPv6 away entirely rather than moving it to another address. Anything that
needs IPv6 breaks during a failover, while IPv4 merely changes address.

The Neko container follows the host. That is not automatic: Tailscale routes
the local subnets into the tunnel alongside the default route, to stop traffic
leaking onto an untrusted LAN, and podman's `10.88.0.0/16` is one of them. The
first deploy here cut the container off the internet entirely while the host
was fine, with DNS still resolving through the host to make it look like
something else. `--exit-node-allow-lan-access` turns those routes into `throw`.
So check both when this misbehaves, not just the host:

```
curl https://api.ipify.org; echo
pid=$(sudo podman inspect neko --format '{{.State.Pid}}')
sudo nsenter -t "$pid" -n curl https://api.ipify.org; echo
```

```
systemctl status tailscale-exit-node
journalctl -u tailscale-exit-node -n 20
tailscale status | head -1
curl https://api.ipify.org; echo
```

A switch takes up to 30 seconds plus the probe, so a failover looks like a
brief stall rather than an instant change.

Both home hosts take the `exit-node` trait, which turns on forwarding and
advertises them. Advertising is not enough on its own: the route needs
approval once in the admin console under the machine's route settings, and a
newly reinstalled host needs it again. An unapproved host reports
`ExitNodeOption: false` and this unit skips it, which reads exactly like the
host being down. `tailscale set` also refuses the selection outright in that
state, so the selector treats a refusal as another reason to try the next
candidate.

### Inbound traffic keeps its own path

A default route into the tunnel would also swallow the replies to connections
that arrived on the public IP, and SSH from outside the tailnet would die the
moment an exit node came up. `exit-node-bypass-rule` prevents that: nftables
marks connections that enter from a non-tailnet interface *and are addressed to
this host*, the mark is restored on reply packets, and an `ip rule` at priority
5000, ahead of Tailscale's own at 5270, sends those replies back to the main
table.

The `fib daddr type local` half of that rule is load-bearing. Without it the
mark also lands on traffic merely passing through this host, which is exactly
the Neko container's egress, and the browser would leave from the public IP
while everything else left from home.

So this host is asymmetric on purpose. New outbound connections go through
home; anything answering an inbound connection goes back the way it came.

```
ip rule show | grep 5000
sudo nft list table inet exit-node-bypass
```

That claim is testable without the host. `./scripts/test-exit-node-bypass`
builds new-horizons, loads its real firewall into an unprivileged network
namespace behind a blackholing default route standing in for the exit node, and
checks that an inbound TCP connection completes while a new outbound one does
not. It starts by confirming the same connection breaks without the bypass, so
a passing run means something.

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
| `https://new-horizons.taile99a6c.ts.net:8444` | OwnTracks receiver  |

Both are Serve, not Funnel, so they exist only inside the tailnet. Port 22 is
the only thing answering on the public address.

The Control UI opens from any tailnet device with the gateway token,
`OPENCLAW_GATEWAY_TOKEN` in `openclaw-env`. The gateway used to claim the
Serve route itself and accept tailnet identity headers instead of a token,
but since 2026.9 that claim is a hard startup requirement and the service user
can neither run `tailscale serve` nor reach sudo, so the gateway could not
start at all. `tailscale-serve` owns every route now, `gateway.tailscale.mode`
is `off`, and loopback is a trusted proxy so forwarded client addresses are
still honoured. Requests to `/api/*` answer `401` without the token.

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

Build on charon, which has the cores and the cache, and send the result. This
host has 4 vCPUs and builds anything uncached slowly while holding the Nix store
lock:

```
nixos-rebuild switch --flake .#new-horizons \
  --target-host potb@new-horizons --elevate sudo
```

The closure is built locally and copied over the tailnet; only activation runs
here.

## What the agent owns

Nix owns the package, the unit and the base config in
`/etc/openclaw/openclaw.json`. The agent owns everything under
`/var/lib/openclaw`: its databases, sessions, memory and cron jobs, plus two
config sections it can edit at runtime, `mcp` and `skills`.

The gateway does not read `/etc` directly. That file is bind-mounted read-only
over `/var/lib/openclaw/config/openclaw.json`, and its `mcp` and `skills`
sections are `$include`s of `mcp.json5` and `skills.json5` in the same
directory, which belong to the `openclaw` user. When the agent (or `/config`,
`/mcp`) changes a key inside one of those sections, OpenClaw writes through to
the included file and leaves the base untouched. A change to any other key
fails with `EBUSY` on the rename over the bind mount, so the base stays
exactly what Nix built. To hand another section to the agent, add it to
`agentOwnedSections` and give it an `$include` in the config.

This needs `OPENCLAW_NIX_MODE=0` in the unit: Nix mode refuses every config
write before it looks at includes, even ones that would land in the agent's
own files. The package wrapper sets it to `1` by default, the unit overrides
it. What Nix mode also blocked is disabled by config instead: update checks
and auto-updates are off, so the package still only changes through a
rebuild. Do not set any key in Nix that lives inside an agent-owned section:
a sibling key next to an `$include` overrides the included value.

Schema migrations run from `ExecStartPre` rather than by hand. An upgrade can
move the state databases to a newer schema, and the gateway then refuses to
start (`status=78/CONFIG`, `gateway.maintenance_required`) until
`openclaw doctor --fix` migrates them. The pre-start script runs doctor once
per package and config generation, against a disposable copy of the config in
`/var/lib/openclaw/doctor`, after writing `pre-migrate.tgz` of the databases
next to it. Delete `doctor/stamp` to force it to run again. A failed doctor
run does not block the start; the gateway then prints the real error in
`/var/lib/openclaw/logs/gateway.log`.

Owner-only tools (`cron`, `gateway`, `nodes`) follow the turn's requester,
which is `commands.ownerAllowFrom`. Turns the gateway starts on its own, such
as the heartbeat, run without them, so a scheduled job has to be created from
a message sent by that account.

From a Discord turn the agent sees only the automations it created from that
same conversation. A job created with `openclaw automations add` on the host
is operator-owned: it runs and delivers normally, but the agent's list comes
back with `scope: "caller"` and leaves it out, so asking hal for its jobs
looks as if nothing is scheduled. Manage those from the CLI or the Control UI
Automations page, whose administrator turns see the whole Gateway.

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

- The Discord plugin cannot come from the Nix store. Since 2026.9.4 OpenClaw
  lets only bundled plugins and ones with an official install record open
  keyed storage, and a Nix path in `plugins.load.paths` has no install record,
  so Discord fails to register with `openKeyedStore is only available for
  trusted plugins` while the gateway otherwise reports ready (upstream
  nix-openclaw#158). The pre-start script installs `@openclaw/discord` from npm
  at the gateway's own version whenever the trusted install differs, and the
  unit reads the persisted plugin registry so the gateway sees that record.
  Check it with:

  ```
  sudo -u openclaw env OPENCLAW_STATE_DIR=/var/lib/openclaw \
    OPENCLAW_CONFIG_PATH=/var/lib/openclaw/doctor/openclaw.json \
    OPENCLAW_DISABLE_PERSISTED_PLUGIN_REGISTRY=0 HOME=/var/lib/openclaw \
    openclaw plugins inspect discord --json | jq .plugin.trust
  ```

  `reason` must be `trusted-official`.

- OpenClaw 2026.9.5 takes its gateway lock through `openat2`, and systemd's
  `RestrictSUIDSGID` seccomp filter answers every `openat2` with `ENOSYS`,
  because the syscall's mode argument sits in a struct the filter cannot
  inspect. The gateway then dies at start with `openat2 beneath root: Function
  not implemented (os error 38)`, and the pre-start doctor fails the same way.
  The units here leave `RestrictSUIDSGID` off; `NoNewPrivileges` and an empty
  capability set already keep a set-id bit from granting anything. To check a
  candidate sandbox before deploying:

  ```
  sudo systemd-run --pipe --wait -p User=openclaw -p RestrictSUIDSGID=yes \
    python3 -c 'import ctypes,os;l=ctypes.CDLL(None,use_errno=True);print(l.syscall(437,-100,b"/",b"\0"*24,24),os.strerror(ctypes.get_errno()))'
  ```

- An OpenClaw upgrade is one-way. The pre-start doctor migrates the databases
  to the new schema even when the new gateway then fails to start, and the old
  build refuses the newer schema, so rolling the system generation back leaves
  the agent down. `doctor/pre-migrate.tgz` is rewritten on every doctor run,
  including the failed ones, so it cannot be trusted after a second attempt;
  the nightly restic snapshot is the real way back. Build and test a new gateway
  on charon before a switch, and never rebuild on this host: it builds slowly
  and holds the Nix store lock for the duration.

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
