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


def _sensitive(args, info):
    return bool(args.sensitive or info.get("sensitive"))


def _copy_transcript(cfg, args, info):
    if not args.transcript or not info.get("dir"):
        return
    source = Path(args.transcript)
    target = _allowed(cfg, info["dir"]) / source.name
    if source.is_file() and source.resolve() != target.resolve():
        shutil.copy2(source, target)


def _info_thread(info):
    return {
        "slack_ts": info.get("slack_ts"),
        "slack_channel": info.get("slack_channel"),
        "slack_files": list(info.get("slack_files", [])),
    }


def _reusable(cfg, record, sensitive):
    from . import slack

    if not record or not record.get("slack_ts") or not record.get("slack_channel"):
        return False
    return not sensitive or slack.is_dm(cfg, record["slack_channel"])


def _open_thread(cfg, st, mid, info, title, meeting, sensitive):
    from . import slack

    pending = state.thread(st, mid)
    if _reusable(cfg, pending, sensitive):
        return dict(pending), False
    stored = _info_thread(info)
    if _reusable(cfg, stored, sensitive):
        state.save_thread(cfg.state_path, st, mid, stored)
        return stored, True
    ts, channel = slack.post_header(cfg, title, meeting, sensitive)
    record = {"slack_ts": ts, "slack_channel": channel, "slack_files": []}
    state.save_thread(cfg.state_path, st, mid, record)
    return record, False


def _upload(cfg, st, mid, record, kind, path, title):
    from . import slack

    if not path or kind in record["slack_files"]:
        return
    slack.upload(
        cfg, record["slack_channel"], record["slack_ts"], path, slack.file_title(title, kind.capitalize())
    )
    record["slack_files"].append(kind)
    state.save_thread(cfg.state_path, st, mid, record)


def _post_notes(cfg, args, st, mid, title, meeting, sensitive):
    record, _ = _open_thread(cfg, st, mid, {}, title, meeting, sensitive)
    _upload(cfg, st, mid, record, "notes", args.notes, title)
    return record


def _post_transcript(cfg, args, st, mid, info, title, meeting, sensitive):
    record, adopted = _open_thread(cfg, st, mid, info, title, meeting, sensitive)
    _upload(cfg, st, mid, record, "transcript", args.transcript, title)
    return state.POSTED if adopted else state.DM_ONLY


def _slack_allowed(cfg, sensitive):
    from . import slack

    return slack.allowed(cfg, bool(sensitive))


def _stage_notes(cfg, args, st, mid, info, title, meeting):
    if info.get("status") in state.TERMINAL | state.RESUME_TRANSCRIPT:
        return f"{mid}: notes already {info['status']}"
    extra = {"dir": str(Path(args.notes).parent) if args.notes else None}
    if args.sensitive:
        extra["sensitive"] = args.sensitive
    if _slack_allowed(cfg, args.sensitive):
        record = _post_notes(cfg, args, st, mid, title, meeting, args.sensitive)
        extra.update(
            slack_ts=record["slack_ts"],
            slack_channel=record["slack_channel"],
            slack_files=record["slack_files"],
        )
        status = state.NOTES_POSTED
    else:
        status = state.NOTES_SAVED
    state.set_processed(st, mid, status=status, **extra)
    state.clear_thread(st, mid)
    return f"{mid}: {status}"


def _stage_transcript(cfg, args, st, mid, info, title, meeting):
    status = info.get("status")
    if status in state.TERMINAL:
        return f"{mid}: transcript already {status}"
    if status not in state.RESUME_TRANSCRIPT:
        raise SystemExit(f"{mid}: transcript stage needs notes_saved, found {status}")
    if not args.dry_run:
        _copy_transcript(cfg, args, info)
    sensitive = _sensitive(args, info)
    post = args.transcript and _slack_allowed(cfg, sensitive)
    final = (
        _post_transcript(cfg, args, st, mid, info, title, meeting, sensitive) if post else state.DONE
    )
    kept = {k: v for k, v in info.items() if k not in ("status", "at")}
    if args.sensitive and not kept.get("sensitive"):
        kept["sensitive"] = args.sensitive
    state.set_processed(st, mid, status=final, **kept)
    state.clear_thread(st, mid)
    return f"{mid}: {final}"


def _whole(cfg, args, st, mid, info, title, meeting):
    if info.get("status") in state.TERMINAL:
        return f"{mid}: already {info['status']}"
    extra = {"dir": str(Path(args.notes).parent) if args.notes else None}
    if args.sensitive:
        extra["sensitive"] = args.sensitive
    status = state.DONE
    if _slack_allowed(cfg, args.sensitive):
        _post_notes(cfg, args, st, mid, title, meeting, args.sensitive)
        status = state.POSTED
    state.set_processed(st, mid, status=status, **extra)
    state.clear_thread(st, mid)
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
                    if not args.dry_run:
                        state.clear_thread(st, args.id)
                    message = f"{args.id}: {state.SKIPPED}"
            elif args.stage == "notes":
                message = _stage_notes(cfg, args, st, args.id, info, title, meeting)
            elif args.stage == "transcript":
                message = _stage_transcript(cfg, args, st, args.id, info, title, meeting)
            else:
                message = _whole(cfg, args, st, args.id, info, title, meeting)
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
