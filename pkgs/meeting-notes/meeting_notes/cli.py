import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from . import state
from .config import Config

NATIVE_TOOLS = ("pw-dump", "pactl", "hyprctl")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _parser():
    parser = argparse.ArgumentParser(prog="meeting-notes")
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.add_parser("watch", help="detect meetings, record them and run the notes pipeline")
    start = sub.add_parser("start", help="start a meeting by hand")
    start.add_argument("--app", default="Manual")
    start.add_argument("--title")
    sub.add_parser("stop", help="stop the meeting started by hand")
    status = sub.add_parser("status", help="show the active meeting and the last runs")
    status.add_argument("--json", action="store_true")
    sub.add_parser("pending", help="print the fetched meetings waiting for notes as JSON")
    fetch = sub.add_parser("fetch", help="transcribe one meeting into work/<id>")
    fetch.add_argument("id")
    diarize = sub.add_parser("diarize", help="split the others track of one meeting into speakers")
    diarize.add_argument("id")
    diarize.add_argument("--out", help="folder for speakers.json, work/<id> by default")
    voices = sub.add_parser("voices", help="list, add, import or remove voice prints")
    actions = voices.add_subparsers(dest="action", metavar="action", required=True)
    actions.add_parser("list", help="list the voice prints")
    add = actions.add_parser("add", help="build or update a print from a speaker of a diarized meeting")
    add.add_argument("--id", required=True)
    add.add_argument("--speaker", required=True, help="cluster id from speakers.json, such as S2")
    add.add_argument("--name", required=True)
    remove = actions.add_parser("remove", help="delete a voice print")
    remove.add_argument("--name", required=True)
    imported = actions.add_parser("import", help="create a print from a vector in an npz or json file")
    imported.add_argument("--name", required=True)
    imported.add_argument("--file", required=True)
    imported.add_argument("--key", required=True, help="array name in the npz, or key in the json")
    imported.add_argument("--seconds", type=float, default=0.0)
    imported.add_argument("--id", action="append", default=[], help="source meeting id, repeatable")
    sub.add_parser("finish", help="save notes or transcript, see meeting-notes finish --help", add_help=False)
    sub.add_parser("cleanup", help="delete expired audio, screenshots and cache")
    sub.add_parser("screenpipe", help="run the screenpipe recorder with the local API key")
    sub.add_parser("check", help="check tools, models and settings")
    sub.add_parser("slack-check", help="check the Slack token, channel and direct message")
    return parser


def cmd_watch(cfg, args, which):
    from . import watch

    return watch.main(cfg)


def cmd_start(cfg, args, which):
    _write(cfg.control_dir / "start.json", json.dumps({"app": args.app, "title": args.title}))
    print(f"start requested: {args.app}" + (f" / {args.title}" if args.title else ""))
    return 0


def cmd_stop(cfg, args, which):
    _write(cfg.control_dir / "stop", "")
    print("stop requested")
    return 0


def _last_log(cfg):
    if not cfg.runs_dir.is_dir():
        return None
    logs = sorted(p.name for p in cfg.runs_dir.glob("*.log") if "-fetch-" not in p.name)
    return logs[-1] if logs else None


def status_data(cfg):
    st = state.load(cfg.state_path)
    active = state.active_meeting(st)
    done = sorted(st["processed"].items(), key=lambda item: item[1].get("at") or "", reverse=True)[:5]
    return {
        "backend": cfg.backend,
        "live_enabled": cfg.live,
        "active": active,
        "live": active.get("live") if active else None,
        "last_run": {"pending": st.get("last_run"), "log": _last_log(cfg)},
        "processed": [{"id": mid, **info} for mid, info in done],
    }


def cmd_status(cfg, args, which):
    data = status_data(cfg)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    active = data["active"]
    print(f"backend: {data['backend']}, live {'on' if data['live_enabled'] else 'off'}")
    if active:
        print(f"active: {active['id']} {active.get('app')} / {active.get('title')} since {active['start']} "
              f"({active.get('source')}, live {active.get('live')})")
    else:
        print("no active meeting")
    last = data["last_run"]
    print(f"last pending check: {last['pending'] or 'never'}, last claude log: {last['log'] or 'none'}")
    for item in data["processed"]:
        print(f"  {item['id']}: {item.get('status')} at {item.get('at')}")
    return 0


def cmd_pending(cfg, args, which):
    from . import watch

    items = watch.list_ready(cfg, datetime.now(timezone.utc))
    print(json.dumps(items, indent=2, ensure_ascii=False))
    return 0


def _screen_source(cfg, meeting):
    from . import screenpipe

    client = screenpipe.Client(cfg)
    app = meeting.get("app")

    def search_screen(_cfg, start, end):
        return [client.search_screen(state.iso(start), state.iso(end), app).rstrip("\n")]

    return SimpleNamespace(search_screen=search_screen)


def cmd_fetch(cfg, args, which):
    from . import fetch

    meeting = state.load(cfg.state_path)["meetings"].get(args.id)
    if meeting is None:
        print(f"unknown meeting {args.id}", file=sys.stderr)
        return 1
    if not meeting.get("end"):
        print(f"meeting {args.id} has not ended", file=sys.stderr)
        return 1
    screen = _screen_source(cfg, meeting) if meeting.get("backend") == "screenpipe" else None
    try:
        out = fetch.fetch(cfg, args.id, screenpipe=screen)
    except Exception as error:
        print(f"fetch {args.id} failed: {error}", file=sys.stderr)
        return 1
    print(out)
    return 0


def cmd_diarize(cfg, args, which):
    from . import diarize

    try:
        return diarize.main(cfg, args.id, args.out)
    except Exception as error:
        print(f"diarize {args.id} failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


def _voices_list(cfg, args):
    from . import voices

    records = voices.load(cfg.voices_dir)
    if not records:
        print(f"no voice prints in {cfg.voices_dir}")
    for item in records:
        meetings = ", ".join(item.get("meetings") or []) or "-"
        print(f"{item['name']}: {item.get('seconds', 0):.0f} s, meetings {meetings}, confirmed {item.get('confirmed_at')}")
    return 0


def _voices_add(cfg, args):
    import numpy as np

    from . import diarize, voices

    folder = cfg.meeting_dir(args.id)
    try:
        data = json.loads((folder / diarize.SPEAKERS_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise voices.VoiceError(f"meeting {args.id} has no readable {diarize.SPEAKERS_JSON}") from None
    if data.get("status") != "ok":
        raise voices.VoiceError(f"meeting {args.id} was not diarized: {data.get('reason') or data.get('status')}")
    ids = [item["id"] for item in data.get("clusters", [])]
    if args.speaker not in ids:
        raise voices.VoiceError(f"meeting {args.id} has no speaker {args.speaker}, found {', '.join(ids) or 'none'}")
    position = ids.index(args.speaker)
    try:
        with np.load(folder / diarize.SPEAKERS_NPZ, allow_pickle=False) as arrays:
            embeddings, labels = arrays["embeddings"], arrays["labels"]
    except (OSError, KeyError, ValueError):
        raise voices.VoiceError(f"meeting {args.id} has no window embeddings left (cleaned up?)") from None
    chosen = embeddings[labels == position]
    if not len(chosen):
        raise voices.VoiceError(f"speaker {args.speaker} has no windows")
    chosen = chosen / np.linalg.norm(chosen, axis=1, keepdims=True)
    seconds = float(data["clusters"][position]["seconds"])
    existing = voices.find(cfg.voices_dir, args.name)
    entry = voices.merge(existing, args.name, chosen.mean(0), seconds, args.id)
    path = voices.write(cfg.voices_dir, entry)
    verb = "updated" if existing else "created"
    print(f"{verb} {entry['name']} ({entry['seconds']:.0f} s from {len(entry['meetings'])} meetings): {path}")
    return 0


def _voices_remove(cfg, args):
    from . import voices

    path = voices.path_for(cfg.voices_dir, args.name)
    if not path.is_file():
        raise voices.VoiceError(f"no voice print named {args.name}")
    path.unlink()
    print(f"removed {args.name}")
    return 0


def _voices_import(cfg, args):
    from . import voices

    vector = voices.load_vector(args.file, args.key)
    if voices.find(cfg.voices_dir, args.name) is not None:
        raise voices.VoiceError(f"{args.name} already has a print: remove it first")
    entry = voices.record(args.name, vector, args.seconds, args.id)
    path = voices.write(cfg.voices_dir, entry)
    print(f"imported {entry['name']}: {path}")
    return 0


def cmd_voices(cfg, args, which):
    from . import voices

    handler = {
        "list": _voices_list,
        "add": _voices_add,
        "remove": _voices_remove,
        "import": _voices_import,
    }[args.action]
    try:
        return handler(cfg, args)
    except (voices.VoiceError, OSError, ValueError) as error:
        print(f"voices {args.action}: {error}", file=sys.stderr)
        return 1


def cmd_cleanup(cfg, args, which):
    from . import cleanup

    removed = cleanup.run(cfg, datetime.now(timezone.utc))
    print(json.dumps(removed, sort_keys=True))
    return 0


def cmd_screenpipe(cfg, args, which):
    from . import screenpipe

    try:
        screenpipe.exec_server(cfg)
    except OSError as error:
        print(f"cannot start screenpipe: {error}", file=sys.stderr)
        return 1
    return 0


def check_lines(cfg, which=shutil.which):
    tools = [cfg.ffmpeg, cfg.whisper, cfg.claude]
    if cfg.backend == "native":
        tools.extend(NATIVE_TOOLS)
    else:
        tools.append(cfg.screenpipe)
    lines = []
    ok = True
    for tool in tools:
        found = which(tool)
        ok = ok and bool(found)
        lines.append(f"tool {tool}: {found or 'missing'}")
    for label, path in (("model", cfg.model), ("vad model", cfg.vad_model)):
        present = path is not None and Path(path).is_file()
        ok = ok and present
        lines.append(f"{label}: {path if present else 'missing'}")
    if cfg.diarization:
        for label, path in (("speaker model", cfg.speaker_model), ("diarization vad model", cfg.speech_vad_model)):
            present = path is not None and Path(path).is_file()
            ok = ok and present
            lines.append(f"{label}: {path if present else 'missing'}")
        lines.append(f"diarization: on, {cfg.diarization_threads} threads, voices in {cfg.voices_dir}")
    else:
        lines.append("diarization: off")
    lines.append(f"backend: {cfg.backend}")
    lines.append(f"live: {'on' if cfg.live else 'off'}")
    lines.append(f"slack: {'on' if cfg.slack else 'off'}, post to {cfg.slack_post_to}")
    lines.append(f"owner: {cfg.owner}")
    lines.append(f"data: {cfg.data_dir}")
    lines.append(f"meetings: {cfg.meetings_dir}")
    lines.append(f"audio: {cfg.audio_dir}")
    if cfg.backend == "screenpipe":
        lines.append(f"screenpipe url: {cfg.screenpipe_url}")
        lines.append(f"screenpipe key: {'present' if cfg.key_path.is_file() else 'not created yet'}")
    return lines, ok


def cmd_check(cfg, args, which):
    lines, ok = check_lines(cfg, which)
    for line in lines:
        print(line)
    print("ok" if ok else "problems found")
    return 0 if ok else 1


def cmd_slack_check(cfg, args, which):
    from . import slack

    try:
        lines = slack.check(cfg, which=which)
    except slack.SlackError as error:
        print(f"slack-check failed: {error}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    print("ok")
    return 0


COMMANDS = {
    "watch": cmd_watch,
    "start": cmd_start,
    "stop": cmd_stop,
    "status": cmd_status,
    "pending": cmd_pending,
    "fetch": cmd_fetch,
    "diarize": cmd_diarize,
    "voices": cmd_voices,
    "cleanup": cmd_cleanup,
    "screenpipe": cmd_screenpipe,
    "check": cmd_check,
    "slack-check": cmd_slack_check,
}


def _config(environ):
    try:
        return Config.from_env(os.environ if environ is None else environ)
    except ValueError as error:
        print(f"meeting-notes: {error}", file=sys.stderr)
        return None


def main(argv=None, environ=None, which=shutil.which):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["finish"]:
        from . import finish

        cfg = _config(environ)
        if cfg is None:
            return 2
        return finish.main(argv[1:], cfg=cfg)
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    cfg = _config(environ)
    if cfg is None:
        return 2
    try:
        return COMMANDS[args.command](cfg, args, which)
    except KeyboardInterrupt:
        return 130
