import sys
from pathlib import Path

import tomlkit

root = Path(sys.argv[1])
checkouts = sys.argv[2:]

members = []
inherited = {}
for checkout in checkouts:
    manifest_path = root / checkout / "Cargo.toml"
    manifest = tomlkit.parse(manifest_path.read_text())
    workspace = manifest.pop("workspace", None) or {}
    for member in workspace.get("members", []):
        members.append(f"{checkout}/{member}".removesuffix("/."))
    for key in ("package", "dependencies"):
        for name, value in (workspace.get(key) or {}).items():
            if key == "dependencies" and isinstance(value, dict) and "path" in value:
                value["path"] = f"{checkout}/{value['path']}"
            inherited.setdefault(key, {})
            if name in inherited[key] and inherited[key][name] != value:
                sys.exit(f"{checkout} redefines workspace.{key}.{name}")
            inherited[key][name] = value
    patch = manifest.pop("patch", None)
    if patch:
        for registry, entries in patch.items():
            for name, value in entries.items():
                inherited.setdefault("patch", {}).setdefault(registry, {})[name] = value
    manifest.pop("profile", None)
    manifest_path.write_text(tomlkit.dumps(manifest))

combined = tomlkit.document()
workspace = tomlkit.table()
workspace["resolver"] = "2"
workspace["members"] = members
for key in ("package", "dependencies"):
    if key in inherited:
        workspace[key] = inherited[key]
combined["workspace"] = workspace
if "patch" in inherited:
    combined["patch"] = inherited["patch"]
(root / "Cargo.toml").write_text(tomlkit.dumps(combined))
print(f"{len(members)} workspace members")
