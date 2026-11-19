import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import opencode, state

FIXTURE_FILES = ("transcript.txt", "meta.json", "screen.txt", "speakers.json", "fetched.ok")
MEETING_JSON = "meeting.json"
SERVICE_ENV = "service-env.json"
INSTALLED = "installed"
LABELS = "PQRSTUVWXYZ"
STAGGER_SECONDS = 3
JUDGE_MODEL = "claude-agent/opus"
JUDGE_AGENT = "meeting-notes-judge"
JUDGE_TIMEOUT = 3600
NOTES_TIMEOUT = 3 * 3600
NIXOS_FLAG = "__NIXOS_SET_ENVIRONMENT_DONE"
PASSTHROUGH = (
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "TZ",
    "TMPDIR",
    "XDG_RUNTIME_DIR",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "DBUS_SESSION_BUS_ADDRESS",
)
DATA_PLACEHOLDER = "~/.local/share/meeting-notes"
HEADER = re.compile(r"^_.*(\||\u00b7|(?<![^\W\d_])min(?![^\W\d_])).*_\s*$")
COST = re.compile(r"cost ([0-9.]+) USD")
SESSION_LINE = re.compile(r"^session (\S+)$", re.M)


class BenchError(RuntimeError):
    pass


@dataclass
class Runner:
    name: str
    model: str
    pipe: str


@dataclass
class Bac:
    name: str
    fixture: str
    runner: Runner
    result: dict = field(default_factory=dict)


def bench_dir(cfg):
    return cfg.data_dir / "bench"


def fixtures_dir(cfg):
    return bench_dir(cfg) / "fixtures"


def share_file(name):
    parents = Path(__file__).resolve().parents
    candidates = [parents[1] / name]
    if len(parents) > 4:
        candidates.append(parents[4] / "share" / "meeting-notes" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BenchError(f"{name} not found next to the package")


def add_fixture(cfg, mid):
    source = cfg.meeting_dir(mid)
    if not (source / "fetched.ok").is_file():
        raise BenchError(f"meeting {mid} is not fetched: {source}/fetched.ok is missing")
    meeting = state.load(cfg.state_path)["meetings"].get(mid)
    if meeting is None:
        raise BenchError(f"meeting {mid} is not in {cfg.state_path}")
    target = fixtures_dir(cfg) / mid
    if target.exists():
        raise BenchError(f"fixture {mid} already exists: {target}")
    staging = target.with_name(f".{mid}.tmp")
    shutil.rmtree(staging, ignore_errors=True)
    work = staging / "work" / mid
    work.mkdir(parents=True)
    copied = []
    for name in FIXTURE_FILES:
        if (source / name).is_file():
            shutil.copyfile(source / name, work / name)
            copied.append(name)
    if "transcript.txt" not in copied:
        shutil.rmtree(staging)
        raise BenchError(f"meeting {mid} has no transcript.txt")
    (staging / MEETING_JSON).write_text(json.dumps(meeting, indent=2, sort_keys=True, ensure_ascii=False))
    staging.rename(target)
    return target, copied


def list_fixtures(cfg, ids=()):
    root = fixtures_dir(cfg)
    found = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")) if root.is_dir() else []
    if not ids:
        if not found:
            raise BenchError(f"no fixture in {root}")
        return found
    missing = [mid for mid in ids if mid not in found]
    if missing:
        raise BenchError(f"unknown fixture {', '.join(missing)} in {root}")
    return list(ids)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def runners(models, pipes):
    out = []
    for model in models:
        for pipe in pipes or [INSTALLED]:
            out.append(Runner(f"r{len(out) + 1}", model, pipe))
    return out


def plan(fixtures, runner_list):
    return [
        Bac(f"{fixture}-{runner.name}-{slug(runner.model)}", fixture, runner)
        for fixture in fixtures
        for runner in runner_list
    ]


def rewrite(value, moves):
    if isinstance(value, str):
        for old, new in moves:
            if value == old or value.startswith(old + "/"):
                return new + value[len(old):]
        return value
    if isinstance(value, list):
        return [rewrite(item, moves) for item in value]
    if isinstance(value, dict):
        return {key: rewrite(item, moves) for key, item in value.items()}
    return value


def pipe_source(cfg, pipe):
    return cfg.pipe_md if pipe == INSTALLED else Path(pipe)


def bac_data(root, bac):
    return Path(root) / bac.name / "data"


def prepare_bac(cfg, root, bac):
    data = bac_data(root, bac)
    if data.exists():
        raise BenchError(f"{data} already exists")
    (data / "meetings").mkdir(parents=True)
    (data / "work").mkdir()
    plugins = data / ".opencode" / "plugins"
    plugins.mkdir(parents=True)
    text = pipe_source(cfg, bac.runner.pipe).read_text(encoding="utf-8")
    (data / "pipe.md").write_text(text.replace(DATA_PLACEHOLDER, str(data)), encoding="utf-8")
    shutil.copyfile(cfg.glossary, data / "glossary.md")
    settings = json.loads((cfg.data_dir / "opencode.json").read_text(encoding="utf-8"))
    moves = [(str(cfg.data_dir), str(data)), (str(cfg.meetings_dir), str(data / "meetings"))]
    (data / "opencode.json").write_text(json.dumps(rewrite(settings, moves), indent=2))
    for plugin in (cfg.data_dir / ".opencode" / "plugins").glob("*.ts"):
        shutil.copyfile(plugin, plugins / plugin.name)
    if (cfg.data_dir / ".ignore").is_file():
        shutil.copyfile(cfg.data_dir / ".ignore", data / ".ignore")
    fixture = fixtures_dir(cfg) / bac.fixture
    shutil.copytree(fixture / "work" / bac.fixture, data / "work" / bac.fixture)
    meeting = json.loads((fixture / MEETING_JSON).read_text(encoding="utf-8"))
    st = {"version": state.VERSION, "meetings": {bac.fixture: meeting}, "processed": {}, "last_run": None}
    state.save(data / "state.json", st)
    return data


def load_service_env(path):
    try:
        env = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BenchError(f"cannot read the service environment {path}: {error}") from None
    if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
        raise BenchError(f"{path} must hold a JSON object of strings")
    return env


def base_env(service, environ, self_bin):
    env = {key: environ[key] for key in PASSTHROUGH if environ.get(key)}
    env.update(service)
    path = env.get("PATH") or environ.get("PATH", "")
    env["PATH"] = f"{self_bin}:{path}" if self_bin else path
    env[NIXOS_FLAG] = "1"
    return env


def bac_env(base, data, model):
    env = dict(base)
    env.update(
        MEETING_NOTES_DATA_DIR=str(data),
        MEETING_NOTES_MEETINGS_DIR=str(data / "meetings"),
        MEETING_NOTES_SLACK="0",
        MEETING_NOTES_SLACK_TOKEN_FILE="",
        MEETING_NOTES_NOTES_MODEL=model,
    )
    return env


def mask(text):
    out = []
    for line in text.splitlines(keepends=True):
        end = "\n" if line.endswith("\n") else ""
        body = line.rstrip("\n")
        if body.startswith("# "):
            out.append("# [titre masque]" + end)
        elif HEADER.match(body):
            out.append("_[en-tete ou pied masque]_" + end)
        else:
            out.append(line)
    return "".join(out)


def outputs(data):
    folders = sorted(p for p in (Path(data) / "meetings").glob("*/") if (p / "notes.md").is_file())
    if len(folders) != 1:
        return None
    folder = folders[0]
    transcript = folder / "transcript.verbatim.md"
    if not transcript.is_file():
        transcript = folder / "transcript.md"
    if not transcript.is_file():
        return None
    return {"notes": folder / "notes.md", "transcript": transcript}


def draw(bacs, rng=None):
    rng = rng or random.SystemRandom()
    key = {}
    for fixture in dict.fromkeys(bac.fixture for bac in bacs):
        ready = [bac for bac in bacs if bac.fixture == fixture and bac.result.get("outputs")]
        if not ready:
            continue
        if len(ready) > len(LABELS):
            raise BenchError(f"at most {len(LABELS)} runs per fixture")
        rng.shuffle(ready)
        key[fixture] = {label: bac.name for label, bac in zip(LABELS, ready)}
    return key


def judge_settings(judge):
    rule = lambda effect, action, resource: {"action": action, "resource": resource, "effect": effect}
    return {
        "$schema": "https://opencode.ai/config.json",
        "snapshots": False,
        "policies": [rule("deny", "mcp.use", "*"), rule("deny", "skill.use", "*"), rule("deny", "websearch.use", "*")],
        "agents": {
            JUDGE_AGENT: {
                "description": "Grades anonymous meeting notes against the raw transcript, read only",
                "mode": "primary",
                "permissions": [
                    rule("deny", "*", "*"),
                    rule("allow", "read", "*"),
                    rule("deny", "read", "/*"),
                    rule("allow", "read", str(judge)),
                    rule("allow", "read", f"{judge}/*"),
                    rule("deny", "read", "*opencode.json"),
                    rule("deny", "read", "*.opencode/*"),
                    rule("allow", "glob", "*"),
                    rule("allow", "grep", "*"),
                ],
            }
        },
    }


def prepare_judge(cfg, root, bacs, key):
    judge = Path(root) / "judge"
    judge.mkdir()
    by_name = {bac.name: bac for bac in bacs}
    files = []
    for fixture, labels in key.items():
        work = fixtures_dir(cfg) / fixture / "work" / fixture
        for name, target in (("transcript.txt", f"{fixture}-transcript.txt"), ("meta.json", f"{fixture}-meta.json")):
            shutil.copyfile(work / name, judge / target)
            files.append(target)
        for label, name in labels.items():
            for kind, path in by_name[name].result["outputs"].items():
                target = f"{fixture}-{label}-{kind}.md"
                (judge / target).write_text(mask(Path(path).read_text(encoding="utf-8")), encoding="utf-8")
                files.append(target)
    shutil.copyfile(cfg.glossary, judge / "glossary.md")
    pipe = cfg.pipe_md.read_text(encoding="utf-8").replace(f"`{DATA_PLACEHOLDER}`", "the data directory")
    (judge / "pipe.md").write_text(pipe, encoding="utf-8")
    files += ["glossary.md", "pipe.md"]
    (judge / "opencode.json").write_text(json.dumps(judge_settings(judge.resolve()), indent=2))
    plugins = judge / ".opencode" / "plugins"
    plugins.mkdir(parents=True)
    for plugin in (cfg.data_dir / ".opencode" / "plugins").glob("*.ts"):
        shutil.copyfile(plugin, plugins / plugin.name)
    (Path(root) / "key.json").write_text(json.dumps(key, indent=2, sort_keys=True))
    return judge, files


def judge_prompt(cfg, files):
    listing = "\n".join(f"- `{name}`" for name in files)
    return share_file("judge.md").read_text(encoding="utf-8").replace("FILES", listing).replace("OWNER", cfg.owner)


def judge_argv(cfg, model, session_title, prompt):
    return [
        cfg.opencode,
        "run",
        "--standalone",
        "--agent",
        JUDGE_AGENT,
        "--model",
        model,
        "--archived",
        "--format",
        "json",
        "--title",
        session_title,
        prompt,
    ]


def report_text(events):
    parts = [str((event.get("part") or {}).get("text", "")).strip() for event in events if event.get("type") == "text"]
    return "\n\n".join(part for part in parts if part)


def run_cost(data):
    total = 0.0
    for log in (Path(data) / "runs").glob("*.log"):
        if "-fetch-" in log.name:
            continue
        for match in COST.finditer(log.read_text(encoding="utf-8", errors="replace")):
            total += float(match.group(1))
    return total


def run_sessions(data):
    found = []
    for log in (Path(data) / "runs").glob("*.log"):
        found += SESSION_LINE.findall(log.read_text(encoding="utf-8", errors="replace"))
    return found


def start_runs(bacs, root, base, self_cmd, popen=subprocess.Popen, sleep=time.sleep, clock=time.monotonic):
    threads = []
    for index, bac in enumerate(bacs):
        if index:
            sleep(STAGGER_SECONDS)
        data = bac_data(root, bac)
        log = Path(root) / bac.name / "driver.log"
        handle = open(log, "ab")
        started = clock()
        proc = popen(
            [*self_cmd, "run-notes"],
            cwd=data,
            env=bac_env(base, data, bac.runner.model),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        def wait(bac=bac, proc=proc, handle=handle, started=started):
            try:
                code = proc.wait(timeout=NOTES_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait()
            handle.close()
            bac.result.update(exit=code, seconds=round(clock() - started))

        thread = threading.Thread(target=wait, name=f"bench-{bac.name}", daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()


def collect(bacs, root):
    for bac in bacs:
        data = bac_data(root, bac)
        st = state.load(data / "state.json")
        bac.result["status"] = (state.processed(st, bac.fixture) or {}).get("status", "none")
        bac.result["cost"] = run_cost(data)
        bac.result["sessions"] = run_sessions(data)
        found = outputs(data)
        if found:
            bac.result["outputs"] = {kind: str(path) for kind, path in found.items()}


def make_run(env):
    from . import watch

    def run(argv, cwd=None, timeout=watch.DEFAULT_TIMEOUT, log=None):
        handle = open(log, "ab") if log is not None else None
        try:
            try:
                code = subprocess.run(
                    argv,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=handle or subprocess.DEVNULL,
                    stderr=subprocess.STDOUT if handle else subprocess.DEVNULL,
                    timeout=timeout,
                    check=False,
                ).returncode
            except subprocess.TimeoutExpired:
                code = watch.TIMEOUT_CODE
        finally:
            if handle is not None:
                handle.close()
        return subprocess.CompletedProcess(argv, code)

    return run


def run_judge(cfg, root, judge, files, model, run):
    name = f"bench-judge-{Path(root).name}-{opencode.ident()}"
    session_title = opencode.title(name)
    raw = Path(root) / "judge.jsonl"
    scratch = Path(root) / "judge-opencode.json"
    result = run(judge_argv(cfg, model, session_title, judge_prompt(cfg, files)), cwd=judge, timeout=JUDGE_TIMEOUT, log=raw)
    events, other = opencode.read_output(raw)
    (Path(root) / "judge.log").write_text(opencode.render(events, other))
    ids = opencode.owned_sessions(run, cfg, opencode.session_ids(events), session_title, root, scratch)
    report = report_text(events)
    (Path(root) / "report.md").write_text(report + "\n", encoding="utf-8")
    failed = opencode.delete_sessions(run, cfg, list(reversed(ids)), root, scratch)
    return {
        "exit": result.returncode,
        "sessions": ids,
        "failed": failed,
        "cost": opencode.totals(events)["cost"],
        "report": report,
    }


def still_present(run, cfg, ids, cwd):
    scratch = Path(cwd) / "check-opencode.json"
    return [sid for sid in ids if not opencode.gone(run, cfg, sid, cwd, scratch)]


def summary(stamp, bacs, runner_list, key, judge, present, judge_model):
    lines = [f"# meeting-notes bench {stamp}", "", "## Runners", ""]
    for runner in runner_list:
        lines.append(f"- {runner.name}: model `{runner.model}`, pipe `{runner.pipe}`")
    lines += ["", f"Judge: `{judge_model}`", "", "## Runs", ""]
    lines += ["| Bac | Exit | Status | Seconds | Cost USD | Output |", "|---|---|---|---|---|---|"]
    for bac in bacs:
        r = bac.result
        lines.append(
            f"| {bac.name} | {r.get('exit', '-')} | {r.get('status', '-')} | {r.get('seconds', '-')} | "
            f"{r.get('cost', 0.0):.4f} | {'yes' if r.get('outputs') else 'no'} |"
        )
    by_name = {bac.name: bac for bac in bacs}
    lines += ["", "## Key", "", "| Meeting | Label | Bac | Model | Pipe |", "|---|---|---|---|---|"]
    for fixture, labels in key.items():
        for label, name in labels.items():
            runner = by_name[name].runner
            lines.append(f"| {fixture} | {label} | {name} | `{runner.model}` | `{runner.pipe}` |")
    lines += ["", "## Sessions", ""]
    if judge is not None:
        lines.append(f"Judge exit {judge['exit']}, cost {judge['cost']:.4f} USD, sessions {', '.join(judge['sessions']) or 'none'}.")
    checked = sum(len(bac.result.get("sessions", [])) for bac in bacs) + len((judge or {}).get("sessions", []))
    lines.append(f"Checked {checked} sessions through the API, still present: {', '.join(present) or 'none'}.")
    lines += ["", "## Judge report", "", (judge or {}).get("report") or "No judge report.", ""]
    return "\n".join(lines)


def default_out(stamp):
    return Path(os.environ.get("TMPDIR") or "/tmp") / "meeting-notes-bench" / stamp


def run(cfg, fixture_ids, models, pipes, out=None, env_file=None, judge_model=JUDGE_MODEL, environ=None,
        self_cmd=None, run_fn=None, popen=subprocess.Popen, sleep=time.sleep, rng=None, log=print):
    from . import watch

    environ = os.environ if environ is None else environ
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = Path(out) if out else default_out(stamp)
    if root.exists() and any(root.iterdir()):
        raise BenchError(f"{root} is not empty")
    for pipe in pipes:
        if pipe != INSTALLED and not Path(pipe).is_file():
            raise BenchError(f"pipe {pipe} not found")
    resolved_root = root.resolve()
    if resolved_root == cfg.data_dir.resolve() or cfg.data_dir.resolve() in resolved_root.parents:
        raise BenchError(f"{root} is inside {cfg.data_dir}: its opencode.json would merge into every bac")
    fixtures = list_fixtures(cfg, fixture_ids)
    runner_list = runners(models, pipes)
    bacs = plan(fixtures, runner_list)
    self_cmd = list(self_cmd or watch.default_self_cmd())
    self_bin = str(Path(self_cmd[0]).parent) if "/" in self_cmd[0] else ""
    service = load_service_env(env_file or cfg.data_dir / SERVICE_ENV)
    base = base_env(service, environ, self_bin)
    root.mkdir(parents=True, exist_ok=True)
    for bac in bacs:
        prepare_bac(cfg, root, bac)
    log(f"bench in {root}: {len(bacs)} runs")
    start_runs(bacs, root, base, self_cmd, popen=popen, sleep=sleep)
    collect(bacs, root)
    key = draw(bacs, rng)
    run_fn = run_fn or make_run(base)
    judge = None
    if key:
        judge_dir, files = prepare_judge(cfg, root, bacs, key)
        log(f"judging {len(files)} files with {judge_model}")
        judge = run_judge(cfg, root, judge_dir, files, judge_model, run_fn)
    ids = [sid for bac in bacs for sid in bac.result.get("sessions", [])] + list((judge or {}).get("sessions", []))
    present = still_present(run_fn, cfg, ids, root)
    text = summary(stamp, bacs, runner_list, key, judge, present, judge_model)
    (root / "summary.md").write_text(text, encoding="utf-8")
    log(f"summary: {root / 'summary.md'}")
    return root, present


def main(cfg, args, log=print):
    try:
        if args.add_fixture:
            target, copied = add_fixture(cfg, args.add_fixture)
            log(f"fixture {args.add_fixture}: {target} ({', '.join(copied)})")
            return 0
        if not args.model:
            raise BenchError("give at least one --model")
        _, present = run(cfg, args.fixtures, args.model, args.pipe, args.out, args.env, args.judge_model, log=log)
    except (BenchError, OSError) as error:
        print(f"bench: {error}", file=sys.stderr)
        return 1
    return 1 if present else 0
