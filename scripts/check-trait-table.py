import re
import sys

flake_path, readme_path = sys.argv[1], sys.argv[2]

flake = open(flake_path).read()
from_flake = {}
for match in re.finditer(r"(\w[\w-]*) = mkHost \{(.*?)\n      \};", flake, re.S):
    body = match.group(2)
    sets = re.search(r"sets = \[(.*?)\];", body, re.S).group(1)
    from_flake[match.group(1)] = re.findall(r'"([^"]+)"', sets)

readme = open(readme_path).read()
from_readme = {}
for line in readme.splitlines():
    match = re.match(r"\| `([\w-]+)` \| ([a-z0-9 -]+) \|$", line.strip())
    if match:
        from_readme[match.group(1)] = match.group(2).split()

if from_flake == from_readme:
    print(f"trait table matches flake.nix for {len(from_flake)} hosts")
    sys.exit(0)

print("README trait table does not match flake.nix:", file=sys.stderr)
for host in sorted(set(from_flake) | set(from_readme)):
    in_flake = from_flake.get(host)
    in_readme = from_readme.get(host)
    if in_flake != in_readme:
        print(f"  {host}", file=sys.stderr)
        print(f"    flake.nix: {' '.join(in_flake) if in_flake else '(absent)'}", file=sys.stderr)
        print(f"    README.md: {' '.join(in_readme) if in_readme else '(absent)'}", file=sys.stderr)
sys.exit(1)
