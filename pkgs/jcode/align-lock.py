import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

jcode_vendor, desktop_vendor, workspace, scratch = map(Path, sys.argv[1:5])
cargo = os.environ.get("CARGO", "cargo")
workspace_lock = workspace / "Cargo.lock"


def packages(lock):
    return tomllib.loads(lock.read_text())["package"]


def is_registry(pkg):
    return pkg.get("source", "").startswith("registry+")


jcode_lock = packages(jcode_vendor / "Cargo.lock")
desktop_doc = tomllib.loads((desktop_vendor / "Cargo.lock").read_text())
desktop_lock = desktop_doc["package"]


def versions(pkgs):
    index = defaultdict(set)
    for pkg in pkgs:
        if is_registry(pkg):
            index[pkg["name"]].add(pkg["version"])
    return index


jcode_versions = versions(jcode_lock)
desktop_versions = versions(desktop_lock)
widened = set()


def offered(name):
    if name in jcode_versions and name not in widened:
        return jcode_versions[name]
    return desktop_versions.get(name, set()) | jcode_versions.get(name, set())


def git_blocks(vendor):
    text = (vendor / ".cargo" / "config.toml").read_text()
    return [b for b in re.split(r"(?m)^(?=\[source)", text) if b.startswith('[source."git+')]


def write_vendor():
    root = scratch / "vendor"
    if root.exists():
        shutil.rmtree(root)
    registry = root / "registry"
    registry.mkdir(parents=True)
    for name in set(jcode_versions) | set(desktop_versions):
        for version in offered(name):
            entry = f"{name}-{version}"
            in_jcode = version in jcode_versions.get(name, ())
            source = (jcode_vendor if in_jcode else desktop_vendor) / entry
            os.symlink(source.resolve(), registry / entry)
    blocks = [
        '[source.crates-io]\nreplace-with = "vendored-registry"\n',
        f'[source.vendored-registry]\ndirectory = "{registry}"\n',
    ]
    seen = set()
    for label, vendor in (("jcode", jcode_vendor), ("desktop", desktop_vendor)):
        git_dir = root / f"git-{label}"
        git_dir.mkdir()
        for entry in vendor.iterdir():
            if (entry / ".cargo-config").exists():
                os.symlink(entry.resolve(), git_dir / entry.name)
        for block in git_blocks(vendor):
            header = block.splitlines()[0]
            if header not in seen:
                seen.add(header)
                blocks.append(block.replace('"vendored-sources"', f'"vendored-git-{label}"'))
        blocks.append(f'[source.vendored-git-{label}]\ndirectory = "{git_dir}"\n')
    home = scratch / "cargo-home"
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text("\n".join(b if b.endswith("\n") else b + "\n" for b in blocks))
    return home


def write_seed():
    chosen = {}
    for pkg in jcode_lock + desktop_lock:
        if pkg.get("source") is None:
            continue
        if is_registry(pkg):
            if pkg["version"] not in offered(pkg["name"]):
                continue
            if pkg["name"] in widened and pkg["version"] not in desktop_versions.get(pkg["name"], ()):
                continue
        chosen.setdefault((pkg["name"], pkg["version"], pkg["source"]), pkg)
    lines = [f"version = {desktop_doc.get('version', 4)}", ""]
    for pkg in sorted(chosen.values(), key=lambda p: (p["name"], p["version"], p["source"])):
        lines += ["[[package]]", f"name = {json.dumps(pkg['name'])}", f"version = {json.dumps(pkg['version'])}"]
        lines.append(f"source = {json.dumps(pkg['source'])}")
        if pkg.get("checksum"):
            lines.append(f"checksum = {json.dumps(pkg['checksum'])}")
        if pkg.get("dependencies"):
            lines.append("dependencies = [")
            lines += [f" {json.dumps(d)}," for d in pkg["dependencies"]]
            lines.append("]")
        lines.append("")
    workspace_lock.write_text("\n".join(lines))


def cargo_run(home, *args):
    return subprocess.run(
        [cargo, *args, "--offline"],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={**os.environ, "CARGO_HOME": str(home)},
        timeout=300,
    )


NAMES = [
    re.compile(r"failed to select a version for the requirement `([A-Za-z0-9_-]+) = "),
    re.compile(r"failed to select a version for `([A-Za-z0-9_-]+)`"),
    re.compile(r"required by package `([A-Za-z0-9_-]+) v"),
]


def culprit(stderr):
    for pattern in NAMES:
        for name in pattern.findall(stderr):
            if name in desktop_versions and name not in widened:
                return name
    return None


for _ in range(300):
    home = write_vendor()
    write_seed()
    run = cargo_run(home, "metadata", "--format-version", "1")
    if run.returncode == 0:
        break
    name = culprit(run.stderr)
    if name is None:
        sys.exit("cannot resolve the combined workspace:\n" + run.stderr)
    widened.add(name)
else:
    sys.exit("gave up widening")

tried = set()
progress = True
while progress:
    progress = False
    now = versions(packages(workspace_lock))
    for name in sorted(n for n in now if n in jcode_versions and now[n] - jcode_versions[n]):
        for current in sorted(now[name] - jcode_versions[name]):
            for target in sorted(jcode_versions[name] - now[name], reverse=True):
                if (name, current, target) in tried:
                    continue
                tried.add((name, current, target))
                if cargo_run(home, "update", "-p", f"{name}@{current}", "--precise", target).returncode == 0:
                    progress = True
                    break
            if progress:
                break
        if progress:
            break

final = versions(packages(workspace_lock))
report = {
    "sharedWithJcode": sum(len(final[n] & jcode_versions[n]) for n in final if n in jcode_versions),
    "jcodeOnlyVersions": {n: sorted(jcode_versions[n] - final[n]) for n in jcode_versions if jcode_versions[n] - final[n]},
    "addedVersions": {n: sorted(final[n] - jcode_versions[n]) for n in final if n in jcode_versions and final[n] - jcode_versions[n]},
}
(scratch / "alignment.json").write_text(json.dumps(report, indent=1, sort_keys=True))
print(f"{report['sharedWithJcode']} registry crates at jcode's version, {len(report['addedVersions'])} with an extra version for desktop, {len(report['jcodeOnlyVersions'])} jcode versions dropped")
