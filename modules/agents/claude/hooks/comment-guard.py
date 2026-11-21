#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

EDIT_TOOLS = {"edit", "multiedit", "write"}

SLASH_STAR = {
    "c", "h", "cc", "cpp", "hpp", "cxx", "m", "mm", "java", "kt", "kts", "scala",
    "swift", "go", "rs", "js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts",
    "css", "scss", "less", "php", "dart", "zig", "sol", "gradle", "proto",
}
HASH = {
    "py", "rb", "sh", "bash", "zsh", "fish", "pl", "pm", "r", "jl", "nix", "tf",
    "toml", "yaml", "yml", "ini", "cfg", "conf", "just", "mk", "dockerfile",
    "env",
}
SHELL = {"sh", "bash", "zsh", "fish"}
SHELL_WORD_START = set(" \t\n;&|()")
LISTED = 10

DIRECTIVE = re.compile(
    r"^(?:@|#!)|^(?:type:|noqa|pyright:|ruff:|mypy:|pylint:|flake8:|pyre:|pytype:"
    r"|eslint-|prettier-ignore|ts-ignore|ts-expect-error|biome-ignore|clippy:"
    r"|rustfmt:|safety:|cbindgen:|codegen|nolint|go:|#\[|shellcheck|nosec"
    r"|allow\(|deny\(|warn\(|forbid\(|region\b|endregion\b|language=|istanbul "
    r"|c8 ignore|v8 ignore)",
    re.IGNORECASE,
)
BDD = re.compile(r"^(given|when|then|arrange|act|assert|when ?& ?then)\b[:.]?$", re.IGNORECASE)
URL_ONLY = re.compile(r"^<?https?://\S+>?$")
SEPARATOR = re.compile(r"^[-=*_#/~\s]*$")

EXTENSIONS = "|".join(sorted(SLASH_STAR | HASH))
IN_PLACE_EDIT = re.compile(
    r"\b(?:sed|perl)\b[^|;&\n]*?\s(?:-[a-zA-Z]*i[a-zA-Z]*\b|--in-place\b)"
)
INTERPRETER = re.compile(r"\b(?:python3?|perl|ruby|node|deno|bun)\b")
FILE_WRITE_CALL = re.compile(
    r"\.write_text\(|\.write_bytes\(|\.write\(|writeFileSync\(|writeFile\("
    r"|File\.write\(|\bopen\([^)]*[\"'][wax]b?\+?[\"']"
)
SOURCE_PATH = re.compile(r"[\w./${}~-]+\.(?:" + EXTENSIONS + r")\b")
REDIRECT_TARGET = re.compile(
    r"(?:(?<![<>&\d])>>?|\btee\s+(?:-a\s+)?)\s*[\"']?([\w./${}~-]+\.(?:" + EXTENSIONS + r"))\b"
)


def ext_of(path: str) -> str:
    base = os.path.basename(path).lower()
    if "." not in base:
        return base
    return base.rsplit(".", 1)[1]


def strip_markers(text: str) -> str:
    text = text.strip()
    for marker in ("///", "//!", "/**", "/*!", "/*", "*/", "//", "#|", "#"):
        if text.startswith(marker):
            text = text[len(marker) :]
            break
    return text.strip().lstrip("*").strip()


def is_exempt(raw: str) -> bool:
    body = strip_markers(raw)
    if not body:
        return True
    if SEPARATOR.match(raw.strip()):
        return True
    if DIRECTIVE.match(body) or DIRECTIVE.match(raw.strip()):
        return True
    if BDD.match(body):
        return True
    return bool(URL_ONLY.match(body))


def scan(text: str, ext: str) -> list[str]:
    if ext in HASH:
        return scan_hash(text, word_start_only=ext in SHELL)
    if ext in SLASH_STAR:
        return scan_slash(text)
    return []


def scan_hash(text: str, word_start_only: bool = False) -> list[str]:
    found, quote, i, n = [], None, 0, len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if text.startswith(('"""', "'''"), i):
            quote = text[i : i + 3]
            i += 3
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            continue
        if ch == "#" and (not word_start_only or i == 0 or text[i - 1] in SHELL_WORD_START):
            end = text.find("\n", i)
            end = n if end == -1 else end
            found.append(text[i:end])
            i = end
            continue
        i += 1
    return found


def scan_slash(text: str) -> list[str]:
    found, quote, i, n = [], None, 0, len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end == -1 else end
            found.append(text[i:end])
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            found.append(text[i:end])
            i = end
            continue
        i += 1
    return found


def text_of(value: object) -> str:
    return value if isinstance(value, str) else ""


def comments_in(path: str, text: str) -> list[str]:
    ext = ext_of(path)
    if ext in ("md", "mdx", "rst", "txt"):
        return []
    name = os.path.basename(path) or path
    return [
        f"{name}: {raw.strip().splitlines()[0][:120]}"
        for raw in scan(text, ext)
        if not is_exempt(raw)
    ]


def added_texts(tool: str, tool_input: dict) -> list[tuple[str, str]]:
    path = text_of(tool_input.get("file_path"))
    if tool == "write":
        return [(path, text_of(tool_input.get("content")))]
    pairs = []
    if "new_string" in tool_input:
        pairs.append((path, text_of(tool_input.get("new_string"))))
    for entry in tool_input.get("edits") or []:
        if isinstance(entry, dict):
            pairs.append((path, text_of(entry.get("new_string"))))
    return pairs


def git(directory: str, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", directory, *args], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None


def added_lines(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    directory = os.path.dirname(path) or "."
    tracked = git(directory, "ls-files", "--error-unmatch", "--", path)
    if tracked is None or tracked.returncode != 0:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    diff = git(directory, "diff", "--no-color", "-U0", "HEAD", "--", path)
    if diff is None or diff.returncode != 0:
        return None
    return "\n".join(
        line[1:]
        for line in diff.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def bash_write_kind(command: str) -> str:
    if IN_PLACE_EDIT.search(command):
        return "an in-place sed/perl edit"
    if INTERPRETER.search(command) and FILE_WRITE_CALL.search(command):
        return "an inline script that writes files"
    if REDIRECT_TARGET.search(command):
        return "a shell redirect, heredoc or tee"
    return ""


def written_paths(command: str, cwd: str) -> list[str]:
    candidates = [match.group(1) for match in REDIRECT_TARGET.finditer(command)]
    if IN_PLACE_EDIT.search(command) or FILE_WRITE_CALL.search(command):
        candidates += SOURCE_PATH.findall(command)
    paths = [os.path.join(cwd, os.path.expanduser(c)) for c in candidates if "$" not in c]
    return list(dict.fromkeys(paths))


def listing(offenders: list[str]) -> str:
    unique = list(dict.fromkeys(offenders))
    shown = "\n".join(f"  - {o}" for o in unique[:LISTED])
    more = f"\n  - and {len(unique) - LISTED} more" if len(unique) > LISTED else ""
    return shown + more


RULE = (
    "House rule: code carries no explanatory comments, including doc comments. "
    "The explanation goes in the repo docs, and names and structure carry the rest. "
    "Tool directives (eslint-disable, ts-expect-error, noqa, #[allow(...)]) are fine."
)


def edit_notice(tool: str, tool_input: dict) -> str:
    offenders = [
        found for path, text in added_texts(tool, tool_input) for found in comments_in(path, text)
    ]
    if not offenders:
        return ""
    return (
        "Comment check: the edit went through, but it added code comments:\n"
        + listing(offenders)
        + f"\n{RULE}\nRemove these comments now with a follow-up Edit, unless one is a tool directive."
    )


def bash_notice(tool_input: dict, cwd: str) -> str:
    command = text_of(tool_input.get("command"))
    kind = bash_write_kind(command)
    if not kind:
        return ""
    offenders: list[str] = []
    checked: list[str] = []
    for path in written_paths(command, cwd):
        text = added_lines(path)
        if text is None:
            continue
        checked.append(os.path.relpath(path, cwd))
        offenders += comments_in(path, text)
    if offenders:
        return (
            f"Comment check: this command wrote files through {kind}, so no edit tool saw it. "
            "Its added lines carry code comments:\n"
            + listing(offenders)
            + f"\n{RULE}\nRemove them now with Edit, and prefer Edit or Write for the next change."
        )
    if checked:
        return ""
    return (
        f"Comment check: this command looks like it edits files through {kind}, "
        "and the comment check could not tell which files it changed. "
        "Look at what it wrote (git diff) and remove any code comments you added. "
        f"{RULE}"
    )


def notice_for(payload: dict) -> str:
    tool = text_of(payload.get("tool_name")).lower()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    if tool == "bash":
        return bash_notice(tool_input, text_of(payload.get("cwd")) or os.getcwd())
    if tool in EDIT_TOOLS:
        return edit_notice(tool, tool_input)
    return ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        notice = notice_for(payload) if isinstance(payload, dict) else ""
    except Exception:
        return 0
    if notice:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": notice}}
        sys.stdout.write(json.dumps(output) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
