import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import export

PARIS = timezone(timedelta(hours=1))

TRANSCRIPT = """# Mazmez x Costo - Transcript
_Google Meet · 2026-11-18 11:01-11:45 · Participants : Peïo, Hugo Danaguezian (Mazmez), Bastien Peccoux, Quentin Peccoux (+ bot Notta)_

**[11:01] Bastien (?) :** Salut, tu nous entends ?

**[11:01] Peïo :** Salut, ça va.

**[11:02] Hugo :** Premier paragraphe.

**[11:02] Hugo :** Deuxième tour.

**[11:03] Participant 1 (Quentin ?) :** Ok.

**[11:04] Peïo (?) :** Peut-être moi.

**[11:05] Bastien :** Salut.

_Corrections : écho retiré._
"""

NOTES = "\n".join(
    [
        "# Titre",
        "**TL;DR** Resume court.",
        "",
        "## Decisions",
        "- Une decision",
        "",
        "## Actions",
        "- Une action",
        "",
    ]
)


def meeting(mid="20261118-100141", **extra):
    base = {
        "id": mid,
        "title": "Meet - Mazmez x Costo",
        "app": "Google Meet",
        "start": "2026-11-18T10:01:41Z",
        "end": "2026-11-18T10:45:40Z",
    }
    base.update(extra)
    return base


class Slug(unittest.TestCase):
    def test_ascii_lowercase(self):
        self.assertEqual(export.slug("Peïo"), "peio")
        self.assertEqual(export.slug("Hugo Danaguezian"), "hugo-danaguezian")
        self.assertEqual(export.slug("  Éloïse  D'Arc "), "eloise-d-arc")
        self.assertEqual(export.slug("???"), "")


class Parsing(unittest.TestCase):
    def test_participants_drop_parentheses_and_bots(self):
        names, _ = export.parse_transcript(TRANSCRIPT)
        self.assertEqual(names, ["Peïo", "Hugo Danaguezian", "Bastien Peccoux", "Quentin Peccoux"])

    def test_turns_skip_header_and_footer(self):
        _, turns = export.parse_transcript(TRANSCRIPT)
        self.assertEqual(len(turns), 7)
        self.assertEqual(turns[0], {"hour": 11, "minute": 1, "label": "Bastien (?)", "text": "Salut, tu nous entends ?"})
        self.assertNotIn("Corrections", " ".join(t["text"] for t in turns))

    def test_continuation_line_joins_previous_turn(self):
        _, turns = export.parse_transcript("**[09:00] Hugo :** un\nsuite\n")
        self.assertEqual(turns[0]["text"], "un\nsuite")

    def test_empty_turn_dropped(self):
        _, turns = export.parse_transcript("**[09:00] Hugo :**\n")
        self.assertEqual(turns, [])


class Attribution(unittest.TestCase):
    names = ["Peïo", "Hugo Danaguezian", "Bastien Peccoux", "Quentin"]

    def test_owner(self):
        self.assertEqual(export.speaker_peer("Peïo", self.names), "peio")

    def test_unknown_goes_to_colleague(self):
        for label in ("Bastien (?)", "Participant 1 (Quentin ?)", "Peïo (?)", "Participant", "Inconnu", "!!"):
            self.assertEqual(export.speaker_peer(label, self.names), "colleague", label)

    def test_first_name_expands_to_full_name(self):
        self.assertEqual(export.speaker_peer("Hugo", self.names), "hugo-danaguezian")
        self.assertEqual(export.speaker_peer("Quentin", self.names), "quentin")

    def test_unlisted_name_uses_own_slug(self):
        self.assertEqual(export.speaker_peer("Vincent", self.names), "vincent")

    def test_ambiguous_first_name_keeps_slug(self):
        self.assertEqual(export.speaker_peer("Hugo", ["Hugo A", "Hugo B"]), "hugo")


class Splitting(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(export.split_text("abc", 10), ["abc"])

    def test_splits_on_paragraphs(self):
        text = "\n\n".join(["a" * 40, "b" * 40, "c" * 40])
        parts = export.split_text(text, 90)
        self.assertEqual(parts, ["a" * 40 + "\n\n" + "b" * 40, "c" * 40])

    def test_oversized_paragraph_split_on_whitespace(self):
        text = " ".join(["mot"] * 100)
        parts = export.split_text(text, 50)
        self.assertTrue(all(len(p) <= 50 for p in parts))
        self.assertEqual(" ".join(parts).split(), ["mot"] * 100)

    def test_unbreakable_run_is_cut(self):
        parts = export.split_text("x" * 250, 100)
        self.assertEqual([len(p) for p in parts], [100, 100, 50])

    def test_notes_split_on_sections(self):
        parts = export.notes_parts(NOTES, 70)
        self.assertTrue(all(len(p) <= 70 for p in parts))
        self.assertTrue(len(parts) > 1)
        self.assertTrue(parts[0].startswith("# Titre"))
        self.assertTrue(any(p.startswith("## Actions") for p in parts))

    def test_short_notes_single_message(self):
        self.assertEqual(export.notes_parts(NOTES, 4000), [NOTES.strip()])

    def test_blank_notes_empty(self):
        self.assertEqual(export.notes_parts("  \n", 4000), [])


class Messages(unittest.TestCase):
    def build(self, transcript=TRANSCRIPT, notes=NOTES):
        return export.build_messages(meeting(), notes, transcript, tz=PARIS)

    def test_layers_and_peers(self):
        msgs = self.build()
        layers = {(m["peer_id"], m["metadata"]["layer"]) for m in msgs}
        self.assertEqual(
            layers,
            {
                ("colleague", "meeting-transcript"),
                ("peio", "meeting-transcript"),
                ("hugo-danaguezian", "meeting-transcript"),
                ("bastien-peccoux", "meeting-transcript"),
                ("meeting-notes", "meeting-notes"),
            },
        )

    def test_same_speaker_same_minute_merged(self):
        hugo = [m for m in self.build() if m["peer_id"] == "hugo-danaguezian"]
        self.assertEqual(len(hugo), 1)
        self.assertEqual(hugo[0]["content"], "[11:02] Hugo: Premier paragraphe.\n\nDeuxième tour.")

    def test_metadata(self):
        msg = self.build()[0]
        self.assertEqual(msg["metadata"]["meeting_id"], "20261118-100141")
        self.assertEqual(msg["metadata"]["title"], "Meet - Mazmez x Costo")
        self.assertEqual(msg["metadata"]["app"], "Google Meet")
        self.assertEqual(msg["metadata"]["start"], "2026-11-18T10:01:41Z")
        self.assertEqual(msg["metadata"]["end"], "2026-11-18T10:45:40Z")
        self.assertEqual(msg["metadata"]["speaker"], "Bastien (?)")

    def test_local_time_converted_to_utc(self):
        self.assertEqual(self.build()[0]["created_at"], "2026-11-18T10:01:00Z")

    def test_notes_after_transcript(self):
        msgs = self.build()
        self.assertEqual(msgs[-1]["peer_id"], "meeting-notes")
        self.assertEqual(msgs[-1]["created_at"], "2026-11-18T10:45:40Z")

    def test_midnight_crossing(self):
        transcript = "**[23:58] Hugo :** avant\n\n**[00:02] Hugo :** apres\n"
        item = meeting(start="2026-11-18T22:55:00Z", end="2026-11-18T23:10:00Z")
        msgs = export.build_messages(item, "", transcript, tz=PARIS)
        self.assertEqual([m["created_at"] for m in msgs], ["2026-11-18T22:58:00Z", "2026-11-18T23:02:00Z"])

    def test_every_message_within_limit(self):
        long_turn = "**[11:01] Hugo :** " + " ".join(["parole"] * 2000) + "\n"
        msgs = self.build(transcript=long_turn, notes="n " * 5000)
        self.assertTrue(len(msgs) > 4)
        self.assertTrue(all(len(m["content"]) <= export.MAX_MESSAGE for m in msgs))
        parts = [m["metadata"].get("part") for m in msgs if m["metadata"]["layer"] == "meeting-transcript"]
        self.assertEqual(parts[0], f"1/{len(parts)}")

    def test_notes_only(self):
        msgs = self.build(transcript="")
        self.assertEqual({m["peer_id"] for m in msgs}, {"meeting-notes"})

    def test_nothing_to_export(self):
        self.assertEqual(self.build(transcript="", notes=""), [])


class Eligibility(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / "meetings" / "a").mkdir(parents=True)
        (self.base / "meetings" / "a" / "notes.md").write_text("n")
        (self.base / "meetings" / "b").mkdir(parents=True)
        (self.base / "meetings" / "b" / "transcript.md").write_text("t")
        (self.base / "meetings" / "empty").mkdir(parents=True)

    def state(self, **processed):
        meetings = {mid: meeting(mid) for mid in processed}
        return {"meetings": meetings, "processed": processed}

    def ids(self, st):
        return [m["id"] for m in export.eligible(st, self.base)]

    def test_relative_and_absolute_dir(self):
        absolute = str(self.base / "meetings" / "b")
        st = self.state(a={"status": "done", "dir": "meetings/a"}, b={"status": "posted", "dir": absolute})
        self.assertEqual(self.ids(st), ["a", "b"])

    def test_terminal_statuses_only(self):
        st = self.state(
            a={"status": "notes_saved", "dir": "meetings/a"},
            b={"status": "notes_posted", "dir": "meetings/b"},
        )
        self.assertEqual(self.ids(st), [])

    def test_skipped_excluded(self):
        st = self.state(
            a={"status": "skipped", "dir": "meetings/a"},
            b={"status": "skipped_short", "dir": "meetings/b"},
        )
        self.assertEqual(self.ids(st), [])

    def test_skip_reason_excluded(self):
        st = self.state(a={"status": "done", "dir": "meetings/a", "skip_reason": "perso"})
        self.assertEqual(self.ids(st), [])

    def test_sensitive_excluded(self):
        st = self.state(
            a={"status": "done", "dir": "meetings/a", "sensitive": True},
            b={"status": "dm_only", "dir": "meetings/b", "sensitive": "rh"},
        )
        self.assertEqual(self.ids(st), [])

    def test_sensitive_on_meeting_record_excluded(self):
        st = self.state(a={"status": "done", "dir": "meetings/a"})
        st["meetings"]["a"]["sensitive"] = True
        self.assertEqual(self.ids(st), [])

    def test_missing_dir_or_files_excluded(self):
        st = self.state(
            a={"status": "done"},
            b={"status": "done", "dir": "meetings/empty"},
            c={"status": "done", "dir": "meetings/absent"},
        )
        self.assertEqual(self.ids(st), [])

    def test_unfinished_meeting_excluded(self):
        st = self.state(a={"status": "done", "dir": "meetings/a"})
        st["meetings"]["a"]["end"] = None
        self.assertEqual(self.ids(st), [])

    def test_unprocessed_excluded(self):
        st = {"meetings": {"a": meeting("a")}, "processed": {}}
        self.assertEqual(self.ids(st), [])

    def test_files_reported(self):
        st = self.state(a={"status": "done", "dir": "meetings/a"}, b={"status": "done", "dir": "meetings/b"})
        found = {m["id"]: m for m in export.eligible(st, self.base)}
        self.assertIsNotNone(found["a"]["notes"])
        self.assertIsNone(found["a"]["transcript"])
        self.assertIsNone(found["b"]["notes"])
        self.assertIsNotNone(found["b"]["transcript"])


class FakeHoncho:
    def __init__(self, fail_after=None):
        self.sessions = {}
        self.peers = []
        self.posts = []
        self.fail_after = fail_after

    def __call__(self, method, path, body=None, quiet=False):
        if path == "/peers":
            self.peers.append(body["id"])
            return {}
        sid = path.split("/")[2]
        if path.endswith("/messages/list"):
            items = [{"id": f"{sid}-{i}", "peer_id": m["peer_id"], "content": m["content"]} for i, m in enumerate(self.sessions.get(sid, []))]
            return {"items": items[:50]}
        if self.fail_after is not None and len(self.posts) >= self.fail_after:
            return None
        self.posts.append((sid, len(body["messages"])))
        self.sessions.setdefault(sid, []).extend(body["messages"])
        return {}


class Idempotence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        folder = base / "meetings" / "m"
        folder.mkdir(parents=True)
        (folder / "notes.md").write_text(NOTES)
        (folder / "transcript.md").write_text(TRANSCRIPT)
        secret = base / "meetings" / "s"
        secret.mkdir()
        (secret / "notes.md").write_text("secret")
        state = {
            "meetings": {"20261118-100141": meeting(), "20261118-120000": meeting("20261118-120000")},
            "processed": {
                "20261118-100141": {"status": "done", "dir": "meetings/m"},
                "20261118-120000": {"status": "done", "dir": "meetings/s", "sensitive": True},
            },
        }
        self.state_path = base / "state.json"
        self.state_path.write_text(json.dumps(state))
        self.record_path = base / "out" / "meetings.json"
        patches = [
            mock.patch.object(export, "MEETING_STATE", str(self.state_path)),
            mock.patch.object(export, "MEETINGS_RECORD", str(self.record_path)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_export(self, fake, **kw):
        with mock.patch.object(export, "honcho", fake):
            return export.export_meetings(**kw)

    def test_dry_run_makes_no_call_and_writes_nothing(self):
        fake = FakeHoncho()
        self.assertTrue(self.run_export(fake, dry=True))
        self.assertEqual(fake.posts, [])
        self.assertEqual(fake.peers, [])
        self.assertFalse(self.record_path.exists())

    def test_missing_state_is_silent(self):
        self.state_path.unlink()
        fake = FakeHoncho()
        self.assertTrue(self.run_export(fake))
        self.assertEqual(fake.posts, [])

    def test_exports_once_and_never_sensitive(self):
        fake = FakeHoncho()
        self.assertTrue(self.run_export(fake))
        self.assertEqual(list(fake.sessions), ["meeting-20261118-100141"])
        first = len(fake.posts)
        self.assertTrue(first >= 1)
        record = json.loads(self.record_path.read_text())
        self.assertIn("20261118-100141", record["exported"])
        self.assertEqual(record["partial"], {})
        self.assertTrue(self.run_export(fake))
        self.assertEqual(len(fake.posts), first)

    def test_content_check_protects_when_record_is_lost(self):
        fake = FakeHoncho()
        self.run_export(fake)
        stored = len(fake.sessions["meeting-20261118-100141"])
        self.record_path.unlink()
        self.run_export(fake)
        self.assertEqual(len(fake.sessions["meeting-20261118-100141"]), stored)

    def test_failed_batch_retries_only_the_rest(self):
        with mock.patch.object(export, "MEETING_BATCH", 2):
            fake = FakeHoncho(fail_after=1)
            self.assertFalse(self.run_export(fake))
            sid = "meeting-20261118-100141"
            self.assertEqual(len(fake.sessions[sid]), 2)
            record = json.loads(self.record_path.read_text())
            self.assertEqual(record["exported"], {})
            self.assertEqual(record["partial"]["20261118-100141"]["sent"], 2)
            fake.fail_after = None
            self.assertTrue(self.run_export(fake))
            expected = export.meeting_messages(export.eligible(json.loads(self.state_path.read_text()), self.state_path.parent)[0])
            self.assertEqual([m["content"] for m in fake.sessions[sid]], [m["content"] for m in expected])
            record = json.loads(self.record_path.read_text())
            self.assertIn("20261118-100141", record["exported"])
            self.assertEqual(record["partial"], {})

    def test_transport_error_keeps_progress_and_retries(self):
        class Flaky(FakeHoncho):
            def __call__(self, method, path, body=None, quiet=False):
                if path.endswith("/messages") and self.fail_after is not None and len(self.posts) >= self.fail_after:
                    raise TimeoutError("timed out")
                return super().__call__(method, path, body, quiet)

        with mock.patch.object(export, "MEETING_BATCH", 2):
            fake = Flaky(fail_after=1)
            self.assertFalse(self.run_export(fake))
            record = json.loads(self.record_path.read_text())
            self.assertEqual(record["partial"]["20261118-100141"]["sent"], 2)
            fake.fail_after = None
            self.assertTrue(self.run_export(fake))
            sid = "meeting-20261118-100141"
            contents = [m["content"] for m in fake.sessions[sid]]
            self.assertEqual(len(contents), len(set(contents)))

    def test_bad_meeting_does_not_block_the_next(self):
        state = json.loads(self.state_path.read_text())
        state["meetings"]["20261118-090000"] = "garbage"
        state["processed"]["20261118-090000"] = {"status": "done", "dir": "meetings/m"}
        self.state_path.write_text(json.dumps(state))
        folder = self.state_path.parent / "meetings" / "bad"
        folder.mkdir()
        (folder / "transcript.md").write_bytes(b"\xff\xfe broken \x80")
        early = dict(meeting("20261118-080000"))
        state["meetings"]["20261118-080000"] = early
        state["processed"]["20261118-080000"] = {"status": "done", "dir": "meetings/bad"}
        self.state_path.write_text(json.dumps(state))
        fake = FakeHoncho()
        self.run_export(fake)
        self.assertIn("meeting-20261118-100141", fake.sessions)

    def test_record_written_atomically(self):
        record = {"version": 1, "exported": {"x": {}}, "partial": {}}
        export.save_record(self.record_path, record)
        self.assertEqual(json.loads(self.record_path.read_text()), record)
        self.assertFalse(Path(str(self.record_path) + ".tmp").exists())

    def test_corrupt_record_treated_as_empty(self):
        self.record_path.parent.mkdir(parents=True)
        self.record_path.write_text("{")
        record = export.load_record(self.record_path)
        self.assertEqual(record["exported"], {})


if __name__ == "__main__":
    unittest.main()
