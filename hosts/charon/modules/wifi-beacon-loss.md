# WiFi drops on charon: iwlwifi beacon loss

## Symptom

The connection works most of the time, then fails for a few seconds at a time,
several times a day. Nothing is permanently broken, so it looks intermittent and
unattributable from user space.

## Diagnosis

Measured on 2026-08-18 over the preceding three days:

| Signal | Result |
|---|---|
| ICMP to 8.8.8.8 and 1.1.1.1, 20 packets each | 0% loss, 4-8 ms average |
| 20 sequential `getent hosts` lookups | 20/20 success, 121 ms total |
| dnscrypt-proxy | up, single Cloudflare DoH resolver, 7-43 ms rtt, no failures |
| `CTRL-EVENT-BEACON-LOSS` | 32 |
| `CTRL-EVENT-DISCONNECTED` | 15 |

So the link is healthy while it is up, and DNS is healthy. The drops are all at
the 802.11 layer:

```
kernel: iwlwifi 0000:07:00.0: missed beacons exceeds threshold, but receiving data. Stay connected, Expect bugs.
kernel: wlo1: Connection to AP 80:82:fe:3d:fe:f8 lost
wpa_supplicant[1213]: wlo1: CTRL-EVENT-DISCONNECTED bssid=80:82:fe:3d:fe:f8 reason=4 locally_generated=1
```

`locally_generated=1` is the decisive detail: the client tore the association
down, the AP did not. The card was still receiving data frames while missing
beacons, which is the signature of the radio sleeping through beacon intervals
under power save rather than of a weak or congested link.

The recovery path makes the drops longer than they need to be. After losing the
5 GHz BSS (`80:82:fe:3d:fe:f8`, channel 100, signal 95) the card reassociates to
the 2.4 GHz BSS of the same SSID (`80:82:fe:3d:ff:00`, channel 11, signal 79),
which is shared with several neighbouring networks on the same channel. The AP
also sends BSS-transition requests (`WNM: Disassociation Imminent`), so some
band changes are AP-driven and expected.

Two settings were both enabled before the fix:

- `/sys/module/iwlmvm/parameters/power_scheme` = `2` (balanced)
- NetworkManager `802-11-wireless.powersave` = `0` (default, which means the
  daemon default, which is on)

## Fix

In `nixos/modules/networking.nix`:

```nix
boot.extraModprobeConfig = ''
  options iwlwifi power_save=0 uapsd_disable=1
  options iwlmvm power_scheme=1
'';
networking.networkmanager.wifi.powersave = false;
```

Both layers are required. The modprobe options set the driver default at load
time; NetworkManager applies its own power-save setting to each connection after
association and would otherwise re-enable it. `power_scheme=1` is CAM
(continuously aware mode), `uapsd_disable=1` turns off the unscheduled
automatic power-save delivery that also depends on the AP behaving well.

Applied at runtime without a reboot with:

```
nmcli con mod Livebox-FEF8 802-11-wireless.powersave 2
```

`2` means disable in NetworkManager's encoding.

## Verifying

After `nixos-rebuild switch` and a reconnect:

```
cat /sys/module/iwlmvm/parameters/power_scheme   # expect 1
journalctl -k --since -1d | grep -c 'missed beacons'
journalctl --since -1d | grep -c CTRL-EVENT-DISCONNECTED
```

Both counts should fall to roughly zero over a comparable window. If beacon
loss persists with power save off, the cause is the radio environment rather
than the driver, and the next step is pinning the connection to the 5 GHz BSS
(`wifi.bssid`) so the noisy shared 2.4 GHz channel is never used.

## Not the cause

Ruled out during the investigation, recorded so they are not re-checked:

- Packet loss to the internet. Zero over 40 probes.
- DNS resolution or dnscrypt-proxy. Every lookup succeeded; the only journal
  entries are routine four-hourly resolver latency checks.
- The `wifi-pci-rescan` service. That handles a WiFi interface missing at boot,
  a different failure, and it is a no-op once `wlo1` exists.
- Ethernet (`eno2`). Down and unused; all traffic is on `wlo1`.
