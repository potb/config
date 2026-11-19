# chrome

Google Chrome comes from `modules/desktop-apps/chrome.nix`, with the package
and its flags in the `google-chrome` entry of `modules/lib/catalog.nix`.
agent-browser drives the same binary through `AGENT_BROWSER_EXECUTABLE_PATH`.

## Temporary directories in /tmp

Chrome, and above all the headless instances agent-browser starts, leave
`/tmp/com.google.Chrome.*`, `/tmp/.org.chromium.Chromium.*` and
`/tmp/scoped_dir*` behind when they are killed. Over a few days of uptime this
grew to a very large number of entries on charon.

charon keeps `/tmp` on disk and sets `boot.tmp.cleanOnBoot`, so
`systemd-tmpfiles-setup` deletes all of `/tmp` during boot, and nothing after
`sysinit.target` starts until it finishes. With that many entries it took
tens of seconds. The kernel command line has `quiet` and `loglevel=0`, so the
screen stayed black without greetd, the machine looked hung, and rebooting
killed the cleanup so the next boot started over. In November 2026 this
looked like broken NixOS generations, although older generations failed the
same way.

The `e` rules in `chrome.nix` make the daily `systemd-tmpfiles-clean.timer`
delete the contents of those directories once they are older than a day. The
emptied directories go with the stock `q /tmp ... 10d` rule. They are `e`
rules rather than `R` rules on purpose: activation runs
`systemd-tmpfiles --remove`, which would delete the directories of a running
Chrome on every switch.

To check whether `/tmp` is filling up again, count its entries:

```sh
ls -f /tmp | wc -l
```
