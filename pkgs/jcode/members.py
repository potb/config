import json
import os
import subprocess
import sys
from pathlib import Path

workspace, out = Path(sys.argv[1]).resolve(), sys.argv[2]
meta = json.loads(
    subprocess.run(
        [os.environ.get("CARGO", "cargo"), "metadata", "--format-version", "1", "--no-deps", "--offline"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
)
members = {
    pkg["name"]: str(Path(pkg["manifest_path"]).parent.relative_to(workspace))
    for pkg in meta["packages"]
}
Path(out).write_text(json.dumps(members, indent=1, sort_keys=True) + "\n")
print(len(members), "workspace members")
