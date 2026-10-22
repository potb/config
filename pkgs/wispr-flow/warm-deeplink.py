import re
import sys

path = sys.argv[1]
marker = "/*WISPR_NIX_WARM_DEEPLINK*/"

with open(path, encoding="utf-8", errors="surrogateescape") as f:
    src = f.read()

if marker in src:
    sys.exit(0)

anchor = re.compile(
    r'if\(([\w$]+\.[\w$]+)\)(\{const ([\w$]+)=[\w$]+\(([\w$]+)\.find\(([\w$]+)=>\5\.startsWith\("wispr-flow:"\)'
    r'\|\|\5\.startsWith\("wispr-flow/"\)\)\);if\(\3\)return void)'
)
matches = list(anchor.finditer(src))
if len(matches) != 1:
    sys.exit(f"warm deep-link anchor matched {len(matches)} times, expected 1")

match = matches[0]
patched = f'if({match.group(1)}||"linux"===process.platform){marker}{match.group(2)}'
src = src[: match.start()] + patched + src[match.end() :]

with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
    f.write(src)
