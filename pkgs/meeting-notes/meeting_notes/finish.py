import argparse
import dataclasses
import shutil
import sys
from pathlib import Path

from . import state
from .config import Config


def _reason(text):
    return text.strip() or True


def _parser():
    parser = argparse.ArgumentParser(prog="meeting-notes finish")
    parser.add_argument("--id", required=True)
    parser.add_argument("--title")
    parser.add_argument("--stage", choices=("notes", "transcript"))
    parser.add_argument("--notes")
    parser.add_argument("--transcript")
    parser.add_argument("--sensitive", nargs="?", const=True, type=_reason, metavar="REASON")
    parser.add_argument("--skip", nargs="?", const=True, type=_reason, metavar="REASON")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _roots(cfg):
    return [Path(cfg.data_dir) / "meetings", Path(cfg.meetings_dir)]


def _allowed(cfg, path):
    resolved = Path(path).resolve()
    for root in _roots(cfg):
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return resolved
    raise SystemExit(f"{path} is outside the meetings folders")


def _check_paths(cfg, args):
    for path in (args.notes, args.transcript):
        if path:
            _allowed(cfg, path)


def _read(path):
    return Path(path).read_text(encoding="utf-8") if path else ""


def _sensitive(args, info):
    return bool(args.sensitive or info.get("sensitive"))


def _copy_transcript(cfg, args, info):
    if not args.transcript or not info.get("dir"):
        return
    source = Path(args.transcript)
    target = _allowed(cfg, info["dir"]) / source.name
    if source.is_file() and source.resolve() != target.resolve():
        shutil.copy2(source, target)


def _post_notes(cfg, args, title):
    from . import slack

    text = f"*{title}*\n{_read(args.notes)}"
    reply = slack.dm(cfg, text)
    return reply.get("ts"), reply.get("channel")


def _post_transcript(cfg, args, info, title):
    from . import slack

    if info.get("slack_ts"):
        slack.dm(cfg, _read(args.transcript), thread_ts=info["slack_ts"])
        return state.POSTED
    slack.dm(cfg, f"*{title}*\n{_read(args.transcript)}")
    return state.DM_ONLY


def _stage_notes(cfg, args, st, mid, info, title):
    if info.get("status") in state.TERMINAL | state.RESUME_TRANSCRIPT:
        return f"{mid}: notes already {info['status']}"
    extra = {"dir": str(Path(args.notes).parent) if args.notes else None}
    if args.sensitive:
        extra["sensitive"] = args.sensitive
    if cfg.slack and not args.sensitive:
        ts, channel = _post_notes(cfg, args, title)
        extra.update(slack_ts=ts, slack_channel=channel)
        status = state.NOTES_POSTED
    else:
        status = state.NOTES_SAVED
    state.set_processed(st, mid, status=status, **extra)
    return f"{mid}: {status}"


def _stage_transcript(cfg, args, st, mid, info, title):
    status = info.get("status")
    if status in state.TERMINAL:
        return f"{mid}: transcript already {status}"
    if status not in state.RESUME_TRANSCRIPT:
        raise SystemExit(f"{mid}: transcript stage needs notes_saved, found {status}")
    if not args.dry_run:
        _copy_transcript(cfg, args, info)
    post = cfg.slack and not _sensitive(args, info)
    final = _post_transcript(cfg, args, info, title) if post else state.DONE
    kept = {k: v for k, v in info.items() if k not in ("status", "at")}
    if args.sensitive and not kept.get("sensitive"):
        kept["sensitive"] = args.sensitive
    state.set_processed(st, mid, status=final, **kept)
    return f"{mid}: {final}"


def _whole(cfg, args, st, mid, info, title):
    if info.get("status") in state.TERMINAL:
        return f"{mid}: already {info['status']}"
    extra = {"dir": str(Path(args.notes).parent) if args.notes else None}
    if args.sensitive:
        extra["sensitive"] = args.sensitive
    status = state.DONE
    if cfg.slack and not args.sensitive:
        _post_notes(cfg, args, title)
        status = state.POSTED
    state.set_processed(st, mid, status=status, **extra)
    return f"{mid}: {status}"


def main(argv=None, cfg=None):
    args = _parser().parse_args(argv)
    cfg = cfg or Config.from_env()
    if args.dry_run:
        cfg = dataclasses.replace(cfg, slack=False)
    try:
        _check_paths(cfg, args)
        with state.locked(cfg.state_path) as st:
            meeting = st["meetings"].get(args.id)
            if meeting is None:
                print(f"unknown meeting {args.id}", file=sys.stderr)
                return 1
            info = state.processed(st, args.id) or {}
            title = args.title or meeting.get("title") or args.id
            snapshot = dict(info)
            if args.skip:
                if info.get("status") in state.TERMINAL:
                    message = f"{args.id}: already {info['status']}"
                else:
                    reason = {} if args.skip is True else {"skip_reason": args.skip}
                    state.set_processed(st, args.id, status=state.SKIPPED, **reason)
                    message = f"{args.id}: {state.SKIPPED}"
            elif args.stage == "notes":
                message = _stage_notes(cfg, args, st, args.id, info, title)
            elif args.stage == "transcript":
                message = _stage_transcript(cfg, args, st, args.id, info, title)
            else:
                message = _whole(cfg, args, st, args.id, info, title)
            if args.dry_run:
                st["processed"].pop(args.id, None)
                if snapshot:
                    st["processed"][args.id] = snapshot
                message = f"dry-run {message}"
    except SystemExit as error:
        print(error.code, file=sys.stderr)
        return 1
    except Exception as error:
        print(f"{args.id}: {error}", file=sys.stderr)
        return 1
    print(message)
    return 0
