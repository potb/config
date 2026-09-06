"""Check that the packaged WoW-detection code accepts this machine's install.

The upstream auto-detection scans Wine, Lutris, Faugus, and Steam's
`steamapps/common`. A Proton install lives under `steamapps/compatdata/<id>/pfx`
and is never scanned, so the path is configured by hand. This asserts the
detection helpers accept that hand-configured path, which is what decides
whether the app can write AppData.lua once the path is set.

Exits 0 when the install is usable, 1 when it is not, and 77 when no install is
present, so a machine without WoW skips instead of failing.
"""

import sys
from pathlib import Path

from tsm.wow.utils import (
    addon_dir,
    apphelper_dir,
    installed_versions,
    normalize_wow_base,
    wtf_accounts_dir,
)

WOW_BASE = Path(
    "/home/potb/.local/share/Steam/steamapps/compatdata/2962204454/pfx/"
    "drive_c/Program Files (x86)/World of Warcraft"
)

if not WOW_BASE.is_dir():
    print(f"skip: no WoW install at {WOW_BASE}")
    sys.exit(77)

base = normalize_wow_base(WOW_BASE)
versions = installed_versions(base)

print(f"base:     {base}")
print(f"versions: {versions or 'NONE DETECTED'}")

if not versions:
    print("fail: no game version detected, so the app cannot write AppData.lua")
    sys.exit(1)

problems = []
for gv in versions:
    addons = addon_dir(base, gv)
    accounts = wtf_accounts_dir(base, gv)
    print(f"  {gv}: AddOns={addons.is_dir()} WTF/Account={accounts.is_dir()}")
    print(f"  {gv}: AppHelper target={apphelper_dir(base, gv)}")
    if not addons.is_dir():
        problems.append(f"{gv}: AddOns directory missing at {addons}")

if problems:
    for problem in problems:
        print(f"fail: {problem}")
    sys.exit(1)

print("pass: install is usable once wow_path is set in Settings")
