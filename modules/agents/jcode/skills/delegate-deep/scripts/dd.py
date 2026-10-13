#!/usr/bin/env python3
"""Coordination helpers for delegate-deep runs.

Every subcommand is deterministic and file based so that workers never depend
on chat delivery to stay consistent. The run directory holds named locks,
named signals, gate round counters and the run charter.

Exit codes: 0 ok, 2 usage error, 75 timed out waiting for a lock or signal,
76 gate round cap reached. `with-lock` passes through the command's exit code.
"""
from __future__ import annotations

import argparse
import json
import os
import signal as signals
import subprocess
import sys
import time
from pathlib import Path

EXIT_USAGE = 2
EXIT_TIMEOUT = 75
EXIT_CAP = 76
ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def jcode_home() -> Path:
    if os.environ.get("JCODE_RUNTIME_DIR"):
        return Path(os.environ["JCODE_RUNTIME_DIR"]) / "durable-state"
    if os.environ.get("JCODE_HOME"):
        return Path(os.environ["JCODE_HOME"]).expanduser() / "state"
    return Path.home() / ".jcode" / "state"


def die(message: str, code: int = EXIT_USAGE) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def safe_name(kind: str, name: str) -> str:
    mapped = name.replace(":", "_")
    if not mapped or mapped.startswith(".") or any(ch not in ALLOWED for ch in mapped):
        die(f"invalid {kind} name '{name}': use letters, digits, dot, dash, underscore, colon")
    return mapped


def run_dir(raw: str | None) -> Path:
    value = raw or os.environ.get("DD_RUN")
    if not value:
        die("run directory missing: pass --run <dir> or export DD_RUN")
    path = Path(value).expanduser().resolve()
    if not (path / "charter.md").is_file():
        die(f"{path} is not a delegate-deep run directory (no charter.md)")
    return path


def holder() -> str:
    return os.environ.get("JCODE_SESSION_ID") or f"pid-{os.getpid()}"


def now() -> float:
    return time.time()


def unique(path: Path, tag: str) -> Path:
    return path.with_name(f"{path.name}.{tag}-{os.getpid()}-{time.monotonic_ns()}")


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = unique(path, "tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)


def lock_path(run: Path, name: str) -> Path:
    return run / "locks" / f"{safe_name('lock', name)}.lock"


def lock_info(path: Path) -> dict | None:
    info = read_json(path / "owner.json")
    if info is None and path.exists():
        try:
            stamp = path.stat().st_mtime
        except FileNotFoundError:
            return None
        return {"holder": "unknown", "node": "", "reason": "", "acquired": stamp, "ttl": 60}
    return info


def lock_expired(info: dict) -> bool:
    ttl = float(info.get("ttl") or 0)
    return ttl > 0 and now() - float(info.get("acquired") or 0) > ttl


def remove_tree(path: Path) -> None:
    for child in path.glob("*"):
        child.unlink(missing_ok=True)
    try:
        path.rmdir()
    except OSError:
        pass


def same_lock(left: dict | None, right: dict | None) -> bool:
    return bool(left and right) and left.get("acquired") == right.get("acquired") and left.get("holder") == right.get("holder")


def break_lock(path: Path, expected: dict | None = None) -> bool:
    tomb = unique(path, "broken")
    try:
        path.rename(tomb)
    except FileNotFoundError:
        return False
    if expected is not None and not same_lock(read_json(tomb / "owner.json"), expected):
        try:
            os.rename(tomb, path)
        except OSError:
            print(f"warning: lock {path.name} changed hands while breaking it, left at {tomb.name}", file=sys.stderr)
        return False
    remove_tree(tomb)
    return True


def try_acquire(path: Path, node: str, reason: str, ttl: float) -> dict | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = unique(path, "new")
    staging.mkdir()
    payload = {"holder": holder(), "node": node, "reason": reason, "acquired": now(), "ttl": ttl, "pid": os.getpid()}
    (staging / "owner.json").write_text(json.dumps(payload))
    try:
        os.rename(staging, path)
        return {"created": True, **payload}
    except OSError:
        remove_tree(staging)
    info = lock_info(path)
    if info and info.get("holder") == holder():
        return {"created": False, **info}
    if info and lock_expired(info):
        break_lock(path, info)
    return None


def acquire_or_timeout(args: argparse.Namespace, path: Path) -> dict:
    deadline = now() + args.timeout
    while True:
        got = try_acquire(path, args.node, args.reason, args.ttl)
        if got:
            return got
        if now() >= deadline:
            info = lock_info(path) or {}
            held = int(now() - float(info.get("acquired") or now()))
            print(
                f"timeout waiting for lock {args.name}: held by {info.get('holder')} "
                f"(node {info.get('node')}, reason: {info.get('reason')}) for {held}s"
            )
            sys.exit(EXIT_TIMEOUT)
        time.sleep(args.poll)


def cmd_lock(args: argparse.Namespace) -> None:
    run = run_dir(args.run)
    got = acquire_or_timeout(args, lock_path(run, args.name))
    print(f"acquired {args.name}" if got["created"] else f"already held {args.name}")


def cmd_unlock(args: argparse.Namespace) -> None:
    run = run_dir(args.run)
    path = lock_path(run, args.name)
    info = lock_info(path)
    if info is None:
        print(f"{args.name} not held")
        return
    if info.get("holder") != holder() and not args.force:
        die(f"{args.name} is held by {info.get('holder')}, not {holder()}; coordinator may use --force")
    break_lock(path, info)
    print(f"released {args.name}")


def cmd_with_lock(args: argparse.Namespace) -> None:
    command = list(args.command or [])
    if not command:
        die("with-lock needs a command after --")
    run = run_dir(args.run)
    path = lock_path(run, args.name)
    got = acquire_or_timeout(args, path)

    def release(*_: object) -> None:
        if got["created"] and same_lock(lock_info(path), got):
            break_lock(path, got)

    def on_term(signum: int, _frame: object) -> None:
        release()
        sys.exit(128 + signum)

    signals.signal(signals.SIGTERM, on_term)
    signals.signal(signals.SIGHUP, on_term)
    try:
        code = subprocess.call(command)
    finally:
        release()
    sys.exit(128 - code if code < 0 else code)


def cmd_locks(args: argparse.Namespace) -> None:
    run = run_dir(args.run)
    rows = []
    for path in sorted((run / "locks").glob("*.lock")):
        info = lock_info(path) or {}
        age = int(now() - float(info.get("acquired") or now()))
        expired = " EXPIRED" if lock_expired(info) else ""
        rows.append(f"{path.stem}\t{info.get('holder')}\t{info.get('node')}\t{age}s{expired}\t{info.get('reason')}")
    print("\n".join(rows) if rows else "no locks held")


def signal_path(run: Path, name: str) -> Path:
    return run / "signals" / safe_name("signal", name)


def cmd_signal(args: argparse.Namespace) -> None:
    run = run_dir(args.run)
    write_atomic(signal_path(run, args.name), {"by": holder(), "at": now(), "note": args.note})
    print(f"signalled {args.name}")


def cmd_wait(args: argparse.Namespace) -> None:
    run = run_dir(args.run)
    path = signal_path(run, args.name)
    deadline = now() + args.timeout
    while True:
        if args.keep and path.exists():
            info = read_json(path) or {}
            break
        if not args.keep:
            taken = unique(path, "consumed")
            try:
                path.rename(taken)
            except FileNotFoundError:
                taken = None
            if taken is not None:
                info = read_json(taken) or {}
                taken.unlink(missing_ok=True)
                break
        if now() >= deadline:
            print(f"timeout waiting for signal {args.name} after {int(args.timeout)}s")
            sys.exit(EXIT_TIMEOUT)
        time.sleep(args.poll)
    print(f"signal {args.name} set by {info.get('by')}: {info.get('note', '')}")


def cmd_clear(args: argparse.Namespace) -> None:
    run = run_dir(args.run)
    signal_path(run, args.name).unlink(missing_ok=True)
    print(f"cleared {args.name}")


def cmd_round(args: argparse.Namespace) -> None:
    run = run_dir(args.run)
    path = run / "rounds" / safe_name("gate", args.gate)
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset:
        path.unlink(missing_ok=True)
        print(f"gate {args.gate} rounds reset")
        return
    count = int(path.read_text() or 0) if path.exists() else 0
    if count >= args.cap:
        print(f"gate {args.gate} already used {count} of {args.cap} rounds: do not inject, report the gaps")
        sys.exit(EXIT_CAP)
    count += 1
    path.write_text(str(count))
    print(f"gate {args.gate} round {count} of {args.cap}")


def find_swarm_of_session(session: str) -> str | None:
    newest = None
    for path in (jcode_home() / "swarm").glob("*.json"):
        data = read_json(path) or {}
        members = data.get("members") or []
        if isinstance(members, dict):
            members = list(members.values())
        if any(isinstance(m, dict) and m.get("session_id") == session for m in members):
            mtime = path.stat().st_mtime
            if newest is None or mtime > newest[0]:
                newest = (mtime, data.get("swarm_id"))
    return newest[1] if newest else None


def default_swarm_id() -> str | None:
    if os.environ.get("JCODE_SWARM_ID", "").strip():
        return os.environ["JCODE_SWARM_ID"].strip()
    session = os.environ.get("JCODE_SESSION_ID")
    if session:
        return find_swarm_of_session(session) or f"session:{session}"
    return None


def swarm_id_for(args: argparse.Namespace) -> str:
    if args.swarm:
        return args.swarm
    run_value = args.run or os.environ.get("DD_RUN")
    if run_value:
        recorded = Path(run_value).expanduser() / "swarm_id"
        if recorded.is_file():
            return recorded.read_text().strip()
    found = default_swarm_id()
    if not found:
        die("cannot tell which swarm: pass --swarm, or --run with a recorded swarm_id")
    return found


def load_plan(args: argparse.Namespace) -> tuple[Path, dict]:
    swarm_id = swarm_id_for(args)
    sanitized = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "-_") else "_" for ch in swarm_id)
    path = jcode_home() / "swarm" / f"{sanitized}.json"
    data = read_json(path)
    if not data or not (data.get("plan") or {}).get("items"):
        die(f"no task graph for swarm '{swarm_id}' at {path}")
    return path, data["plan"]


def node_rows(plan: dict) -> list[dict]:
    meta = plan.get("node_meta") or {}
    progress = plan.get("task_progress") or {}
    items = plan.get("items", [])
    status = {item["id"]: item.get("status") for item in items}
    deps = {item["id"]: item.get("blocked_by", []) for item in items}
    dead: set[str] = {node for node, value in status.items() if value == "failed"}
    changed = True
    while changed:
        changed = False
        for node, value in status.items():
            if node not in dead and value == "queued" and any(dep in dead for dep in deps[node]):
                dead.add(node)
                changed = True
    rows = []
    resumed = set()
    for node in status:
        base, sep, suffix = node.rpartition("-r")
        if sep and suffix.isdigit() and status[node] == "completed":
            resumed.add(base)
    for item in items:
        node_id = item["id"]
        info = meta.get(node_id) or {}
        artifact = None
        if info.get("artifact_json"):
            try:
                artifact = json.loads(info["artifact_json"])
            except ValueError:
                artifact = {"findings": info["artifact_json"]}
        shown = status[node_id]
        if shown == "queued" and node_id in dead:
            shown = "blocked"
        findings = (artifact or {}).get("findings") or ""
        if node_id in resumed:
            flag = "SUPERSEDED"
        elif findings.lstrip().startswith("BLOCKED:"):
            flag = "BLOCKED"
        else:
            flag = ""
        rows.append(
            {
                "id": node_id,
                "status": shown,
                "flag": flag,
                "kind": info.get("kind"),
                "parent": info.get("parent"),
                "gate": bool(info.get("is_gate")),
                "origin": info.get("origin"),
                "depends_on": deps[node_id],
                "assigned_to": item.get("assigned_to"),
                "checkpoint": (progress.get(node_id) or {}).get("checkpoint_summary"),
                "artifact": artifact,
            }
        )
    return rows


def cmd_nodes(args: argparse.Namespace) -> None:
    path, plan = load_plan(args)
    rows = node_rows(plan)
    print(f"{path}  mode={plan.get('mode')}  version={plan.get('version')}  nodes={len(rows)}")
    for row in rows:
        confidence = str((row["artifact"] or {}).get("confidence", ""))[:40]
        kind = ("gate " if row["gate"] else "") + str(row["kind"])
        print(
            f"{row['id']}\t{row['status']}{(' ' + row['flag']) if row['flag'] else ''}\t{kind}\t"
            f"{row['origin'] or ''}\tconf={confidence}\tparent={row['parent'] or ''}\t"
            f"worker={row['assigned_to'] or ''}\t{row['checkpoint'] or ''}"
        )


def cmd_artifact(args: argparse.Namespace) -> None:
    _, plan = load_plan(args)
    rows = {row["id"]: row for row in node_rows(plan)}
    targets = args.ids or [row_id for row_id, row in rows.items() if row["artifact"]]
    out = {}
    for node_id in targets:
        if node_id not in rows:
            die(f"unknown node {node_id}")
        out[node_id] = rows[node_id]["artifact"]
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_init(args: argparse.Namespace) -> None:
    path = Path(args.dir).expanduser().resolve()
    for sub in ("locks", "signals", "blockers", "rounds", "scratch"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    charter = path / "charter.md"
    if not charter.exists():
        charter.write_text("")
    swarm_id = args.swarm or default_swarm_id()
    if swarm_id:
        (path / "swarm_id").write_text(swarm_id)
    if args.repo:
        sha = subprocess.run(
            ["git", "-C", args.repo, "rev-parse", args.base],
            capture_output=True,
            text=True,
            check=False,
        )
        if sha.returncode != 0:
            die(f"cannot resolve {args.base} in {args.repo}: {sha.stderr.strip()}")
        (path / "base_sha").write_text(sha.stdout.strip())
        (path / "base").write_text(args.base)
    print(f"{path}  swarm={swarm_id or 'unknown'}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="dd.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="run directory (default $DD_RUN)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="create a run directory and record the swarm id")
    init.add_argument("dir")
    init.add_argument("--swarm", help="swarm id (default: the swarm this session belongs to)")
    init.add_argument("--repo", help="repository root: record base_sha for the close-out check")
    init.add_argument("--base", default="main", help="base branch (default main)")
    init.set_defaults(func=cmd_init)

    for name, func, text in (
        ("lock", cmd_lock, "acquire a named lock, waiting up to --timeout"),
        ("with-lock", cmd_with_lock, "run the command after -- while holding a named lock"),
    ):
        lock = sub.add_parser(name, help=text)
        lock.add_argument("name")
        lock.add_argument("--node", default="", help="task-graph node id of the caller")
        lock.add_argument("--reason", default="")
        lock.add_argument("--timeout", type=float, default=100, help="seconds to wait (default 100, below the bash default)")
        lock.add_argument("--poll", type=float, default=3)
        lock.add_argument("--ttl", type=float, default=3600, help="seconds before a held lock counts as abandoned, 0 = never")
        lock.set_defaults(func=func)

    unlock = sub.add_parser("unlock", help="release a lock you hold")
    unlock.add_argument("name")
    unlock.add_argument("--force", action="store_true", help="coordinator only: break someone else's lock")
    unlock.set_defaults(func=cmd_unlock)

    locks = sub.add_parser("locks", help="list held locks")
    locks.set_defaults(func=cmd_locks)

    signal = sub.add_parser("signal", help="set a named signal")
    signal.add_argument("name")
    signal.add_argument("--note", default="")
    signal.set_defaults(func=cmd_signal)

    wait = sub.add_parser("wait", help="wait for a named signal and consume it")
    wait.add_argument("name")
    wait.add_argument("--timeout", type=float, default=100, help="seconds to wait (default 100)")
    wait.add_argument("--poll", type=float, default=3)
    wait.add_argument("--keep", action="store_true", help="do not consume the signal (broadcast-style gates)")
    wait.set_defaults(func=cmd_wait)

    clear = sub.add_parser("clear", help="remove a named signal")
    clear.add_argument("name")
    clear.set_defaults(func=cmd_clear)

    rounds = sub.add_parser("round", help="gates: claim the next inject_gap round, exit 76 past --cap")
    rounds.add_argument("gate")
    rounds.add_argument("--cap", type=int, default=3)
    rounds.add_argument("--reset", action="store_true", help="coordinator: reset the counter on resume")
    rounds.set_defaults(func=cmd_round)

    nodes = sub.add_parser("nodes", help="list task-graph nodes with computed blocked status")
    nodes.add_argument("--swarm", help="swarm id (default: recorded in the run directory)")
    nodes.set_defaults(func=cmd_nodes)

    artifact = sub.add_parser("artifact", help="print complete_node artifacts as JSON")
    artifact.add_argument("ids", nargs="*", help="node ids (default: all with artifacts)")
    artifact.add_argument("--swarm", help="swarm id (default: recorded in the run directory)")
    artifact.set_defaults(func=cmd_artifact)

    argv = sys.argv[1:]
    command: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, command = argv[:split], argv[split + 1 :]
    args = parser.parse_args(argv)
    args.command = command
    args.func(args)


if __name__ == "__main__":
    main()
