import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_notes import detect

UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures" / "native"
T0 = datetime(2026, 11, 17, 9, 0, 0, tzinfo=UTC)


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def no_parent(pid):
    return None


def parents(mapping):
    return lambda pid: mapping.get(pid)


def candidate(name, ignore_pids=()):
    data = fixture(name)
    return detect.match_call(
        detect.parse_pw_dump(data["pw_dump"]),
        detect.parse_clients(data["clients"]),
        ignore_pids,
        (),
        no_parent,
    )


def chrome(state="running", pid=4100):
    return detect.Stream(pid, "chrome", "Google Chrome input", state)


def window(title, cls="google-chrome", pid=4100, address="0x1", focus=-1):
    return detect.Client(address, cls, title, pid, (0, 0), (10, 10), "", focus)


def match(streams, clients, ignore_pids=(), ignore_apps=(), ppid=no_parent):
    return detect.match_call(streams, clients, ignore_pids, ignore_apps, ppid)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def run_sequence(detector, names, poll=5):
    events = []
    for index, name in enumerate(names):
        for event in detector.feed(at(index * poll), candidate(name)):
            events.append((index, event))
    return events


class ParseTest(unittest.TestCase):
    def test_parse_pw_dump_keeps_input_streams_only(self):
        self.assertEqual(detect.parse_pw_dump(fixture("idle")["pw_dump"]), [])
        streams = detect.parse_pw_dump(fixture("meet")["pw_dump"])
        self.assertEqual(
            streams, [detect.Stream(4100, "chrome", "Google Chrome input", "running")]
        )

    def test_parse_pw_dump_reads_string_pids(self):
        streams = detect.parse_pw_dump(fixture("slack_huddle")["pw_dump"])
        self.assertEqual(streams, [detect.Stream(6100, "slack", "Slack", "running")])

    def test_parse_pw_dump_tolerates_missing_fields(self):
        objs = [
            {"type": "PipeWire:Interface:Node"},
            {"type": "PipeWire:Interface:Node", "info": None},
            {
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"media.class": "Stream/Input/Audio"}},
            },
        ]
        self.assertEqual(detect.parse_pw_dump(objs), [detect.Stream(None, "", "", "")])

    def test_parse_pw_dump_reads_monitor_and_passive_flags(self):
        def node(**props):
            base = {"media.class": "Stream/Input/Audio", "application.process.id": 5}
            return {"info": {"state": "running", "props": {**base, **props}}}

        streams = detect.parse_pw_dump(
            [
                node(),
                node(**{"stream.capture.sink": True}),
                node(**{"stream.capture.sink": "true"}),
                node(**{"node.passive": "true"}),
                node(**{"node.passive": False, "stream.capture.sink": "false"}),
            ]
        )
        self.assertEqual(
            [(s.monitor, s.passive) for s in streams],
            [(False, False), (True, False), (True, False), (False, True), (False, False)],
        )

    def test_parse_clients_reads_focus_history(self):
        clients = detect.parse_clients(
            [{"address": "0x1", "pid": 1, "focusHistoryID": 0}, {"address": "0x2", "pid": 2}]
        )
        self.assertEqual([c.focus for c in clients], [0, -1])

    def test_parse_clients(self):
        clients = detect.parse_clients(fixture("meet")["clients"])
        self.assertEqual(
            clients[1],
            detect.Client(
                "0x5600b7",
                "google-chrome",
                "Meet - abc-defg-hij - Google Chrome",
                4100,
                (1280, 40),
                (1280, 1400),
                "180000b7",
            ),
        )


class MatchTest(unittest.TestCase):
    def test_idle_is_nothing(self):
        self.assertIsNone(candidate("idle"))

    def test_meet_tab(self):
        found = candidate("meet")
        self.assertEqual(found.app, "Google Meet")
        self.assertEqual(found.title, "Meet - abc-defg-hij - Google Chrome")
        self.assertEqual(found.window.address, "0x5600b7")

    def test_chrome_without_meet_tab_is_generic_browser(self):
        found = candidate("chrome_no_meet")
        self.assertEqual(found.app, "Google Chrome")
        self.assertEqual(found.title, "Inbox - Gmail - Google Chrome")
        self.assertEqual(found.window.address, "0x5600b7")
        self.assertTrue(found.generic)

    def test_generic_browser_is_named_after_the_browser(self):
        cases = [
            ("chrome", "google-chrome", "Google Chrome"),
            ("chromium", "chromium", "Chromium"),
            ("firefox", "firefox", "Firefox"),
        ]
        for binary, cls, label in cases:
            streams = [detect.Stream(4100, binary, f"{binary} input", "running")]
            found = match(streams, [window("Some Call", cls=cls)])
            self.assertEqual(found.app, label)
            self.assertEqual(match(streams, []).app, label)

    def test_whatsapp_web_in_chrome(self):
        for title in ("WhatsApp - Google Chrome", "(3) WhatsApp - Google Chrome"):
            found = match([chrome()], [window(title)])
            self.assertEqual(found.app, "WhatsApp")
            self.assertEqual(found.title, title)
            self.assertFalse(found.generic)

    def test_teams_web_in_chrome(self):
        found = match([chrome()], [window("Chat | Microsoft Teams - Google Chrome")])
        self.assertEqual(found.app, "Teams")

    def test_other_web_call_apps(self):
        for title, label in [
            ("Zoom Meeting - Google Chrome", "Zoom"),
            ("Zoom Workplace - Google Chrome", "Zoom"),
            ("app.zoom.us - Google Chrome", "Zoom"),
            ("Discord | #general - Google Chrome", "Discord"),
            ("#general | Acme - Discord - Google Chrome", "Discord"),
            ("Jitsi Meet - Google Chrome", "Jitsi"),
            ("standup | Jitsi Meet - Google Chrome", "Jitsi"),
            ("Whereby - Google Chrome", "Whereby"),
            ("team-room - Whereby - Google Chrome", "Whereby"),
            ("Webex - Google Chrome", "Webex"),
            ("Cisco Webex Meetings - Google Chrome", "Webex"),
        ]:
            self.assertEqual(match([chrome()], [window(title)]).app, label, title)

    def test_web_app_titles_do_not_match_unrelated_documents(self):
        for title in (
            "Q3 teams planning - Google Chrome",
            "Teams - Google Chrome",
            "Zoom pricing comparison - Google Chrome",
            "Zoom - Google Chrome",
            "how to build a discord bot - Google Chrome",
            "Why whatsapp is popular - Google Chrome",
            "Jitsi notes - Google Chrome",
            "docs on Webex - Google Chrome",
            "Compare Whereby vs Zoom - Google Chrome",
            "About Zoom Workplace pricing - Google Chrome",
            "Jitsi Meet self-hosting guide - Google Chrome",
        ):
            found = match([chrome()], [window(title)])
            self.assertEqual(found.app, "Google Chrome", title)
            self.assertTrue(found.generic, title)

    def test_firefox_title_suffix_is_stripped_for_anchored_patterns(self):
        streams = [detect.Stream(4100, "firefox", "Firefox", "running")]
        found = match(streams, [window("WhatsApp — Mozilla Firefox", cls="firefox")])
        self.assertEqual(found.app, "WhatsApp")

    def test_web_app_prefers_window_with_stream_pid(self):
        clients = [
            window("Discord - Google Chrome", address="0x1", pid=1),
            window("WhatsApp - Google Chrome", address="0x2", pid=4100),
        ]
        self.assertEqual(match([chrome()], clients).app, "WhatsApp")

    def test_web_app_in_another_browser_class_is_ignored(self):
        clients = [window("WhatsApp - Firefox", cls="firefox", pid=1)]
        found = match([chrome()], clients)
        self.assertEqual(found.app, "Google Chrome")
        self.assertIsNone(found.window)

    def test_unknown_browser_tab_falls_back_to_first_window(self):
        found = match([chrome()], [window("Some Call - Google Chrome")])
        self.assertEqual((found.app, found.title), ("Google Chrome", "Some Call - Google Chrome"))

    def test_browser_without_window_still_detected(self):
        found = match([chrome()], [])
        self.assertEqual(
            (found.app, found.title, found.window), ("Google Chrome", "Google Chrome", None)
        )

    def test_google_meet_landing_page_is_not_meet(self):
        found = match([chrome()], [window("Google Meet - Google Chrome")])
        self.assertEqual(found.app, "Google Chrome")

    def test_generic_browser_prefers_most_recently_focused_window(self):
        clients = [
            window("Docs - Google Chrome", address="0x1", pid=1, focus=3),
            window("Mail - Google Chrome", address="0x2", pid=1, focus=0),
            window("News - Google Chrome", address="0x3", pid=1, focus=2),
        ]
        found = match([chrome()], clients)
        self.assertEqual(found.window.address, "0x2")
        self.assertEqual(found.title, "Mail - Google Chrome")

    def test_generic_browser_never_picks_unrelated_class(self):
        clients = [
            detect.Client("0x9", "slack", "general - Slack", 1, (0, 0), (1, 1), "", 0),
            window("Mail - Google Chrome", address="0x2", pid=1, focus=5),
        ]
        self.assertEqual(match([chrome()], clients).window.address, "0x2")

    def test_generic_browser_prefers_call_titled_window_over_focus(self):
        clients = [
            window("Mail - Google Chrome", address="0x1", pid=1, focus=0),
            window("WhatsApp - Google Chrome", address="0x2", pid=1, focus=4),
        ]
        found = match([chrome()], clients)
        self.assertEqual((found.app, found.window.address), ("WhatsApp", "0x2"))

    def test_unfocused_windows_rank_after_focused_ones(self):
        clients = [
            window("A - Google Chrome", address="0x1", pid=1, focus=-1),
            window("B - Google Chrome", address="0x2", pid=1, focus=7),
        ]
        self.assertEqual(match([chrome()], clients).window.address, "0x2")

    def test_meet_wins_over_web_app_title(self):
        clients = [
            window("WhatsApp - Google Chrome", address="0x1"),
            window("Meet - abc-defg-hij - Google Chrome", address="0x2"),
        ]
        self.assertEqual(match([chrome()], clients).app, "Google Meet")

    def test_specific_rule_on_later_stream_wins_over_generic_earlier(self):
        streams = [
            detect.Stream(900, "obs", "OBS", "running"),
            detect.Stream(5200, "zoom", "ZOOM VoiceEngine", "running"),
        ]
        clients = [window("Zoom Meeting", cls="zoom", pid=5200)]
        self.assertEqual(match(streams, clients).app, "Zoom")

    def test_unknown_native_app_uses_window_class_and_title(self):
        streams = [detect.Stream(900, "/nix/store/x/bin/signal-desktop", "Signal", "running")]
        clients = [window("Signal", cls="signal", pid=900)]
        found = match(streams, clients)
        self.assertEqual((found.app, found.title), ("signal", "Signal"))

    def test_unknown_native_app_without_window_uses_stream_name(self):
        streams = [detect.Stream(900, "voicechat", "Voice Chat", "running")]
        found = match(streams, [])
        self.assertEqual((found.app, found.title, found.window), ("Voice Chat", "Voice Chat", None))

    def test_unknown_native_app_falls_back_to_binary_name(self):
        streams = [detect.Stream(900, "/bin/voicechat", "", "running")]
        self.assertEqual(match(streams, []).app, "voicechat")

    def test_idle_stream_ignored_for_generic(self):
        self.assertIsNone(match([detect.Stream(900, "voicechat", "Voice", "idle")], []))
        self.assertIsNone(match([chrome(state="idle")], [window("WhatsApp - Google Chrome")]))
        self.assertIsNone(match([chrome(state="idle")], [window("Inbox - Google Chrome")]))

    def test_idle_stream_still_matches_known_rules(self):
        found = match([chrome(state="idle")], [window("Meet - abc-defg-hij - Google Chrome")])
        self.assertEqual(found.app, "Google Meet")
        streams = [detect.Stream(5200, "zoom", "zoom", "idle")]
        self.assertEqual(match(streams, []).app, "Zoom")

    def test_mic_utilities_are_ignored(self):
        for binary in (
            "pw-record",
            "pw-cat",
            "parecord",
            "parec",
            "arecord",
            "rec",
            "sox",
            "ffmpeg",
            "whisper-cli",
            ".whisper-cli-wrapped",
            "whisper-stream",
            "meeting-notes",
            ".meeting-notes-wrapped",
        ):
            streams = [detect.Stream(900, f"/nix/store/x/bin/{binary}", "", "running")]
            self.assertIsNone(match(streams, []), binary)

    def test_ignore_apps_matches_substrings_case_insensitively(self):
        streams = [detect.Stream(900, "voicechat", "Voice Chat", "running")]
        clients = [window("Room", cls="VoiceClass", pid=900)]
        self.assertIsNotNone(match(streams, clients))
        for needle in ("VOICEC", "chat", "voiceclass"):
            self.assertIsNone(match(streams, clients, ignore_apps=[needle]), needle)
        self.assertIsNotNone(match(streams, clients, ignore_apps=["other", ""]))

    def test_ignore_apps_applies_to_known_rules(self):
        self.assertIsNone(match([chrome()], [window("WhatsApp - Google Chrome")], ignore_apps=["chrome"]))
        streams = [detect.Stream(5200, "zoom", "zoom", "running")]
        self.assertIsNone(match(streams, [], ignore_apps=["zoom"]))

    def test_slack_huddle(self):
        found = candidate("slack_huddle")
        self.assertEqual(found.app, "Slack")
        self.assertEqual(found.window.address, "0x5600c1")

    def test_slack_without_huddle_is_nothing(self):
        data = fixture("slack_huddle")
        data["clients"][0]["title"] = "general - Acme - Slack"
        streams = detect.parse_pw_dump(data["pw_dump"])
        clients = detect.parse_clients(data["clients"])
        self.assertIsNone(match(streams, clients))

    def test_zoom_by_binary_with_window_of_same_pid(self):
        found = candidate("zoom")
        self.assertEqual(found.app, "Zoom")
        self.assertEqual(found.title, "Zoom Meeting")
        self.assertEqual(found.window.address, "0x5600d4")

    def test_app_name_match_is_case_insensitive_and_window_by_class(self):
        streams = [detect.Stream(900, "electron", "Discord", "running")]
        clients = [detect.Client("0x1", "discord", "General - Discord", 901, (0, 0), (10, 10))]
        found = match(streams, clients)
        self.assertEqual(found.app, "Discord")
        self.assertEqual(found.window.address, "0x1")

    def test_app_without_window(self):
        streams = [detect.Stream(900, "teams-for-linux", "teams-for-linux", "running")]
        found = match(streams, [])
        self.assertEqual(found.app, "Teams")
        self.assertIsNone(found.window)

    def test_sink_monitor_streams_are_ignored_by_every_rule(self):
        cases = [
            ([detect.Stream(4100, "chrome", "Google Chrome input", "running", True)], [window("Meet - abc-defg-hij - Google Chrome")]),
            ([detect.Stream(4100, "chrome", "Google Chrome input", "running", True)], [window("WhatsApp - Google Chrome")]),
            ([detect.Stream(4100, "chrome", "Google Chrome input", "running", True)], [window("Inbox - Google Chrome")]),
            ([detect.Stream(900, "voicechat", "Voice", "running", True)], []),
            ([detect.Stream(5200, "zoom", "zoom", "running", True)], []),
        ]
        for streams, clients in cases:
            self.assertIsNone(match(streams, clients))

    def test_passive_streams_are_ignored_by_every_rule(self):
        cases = [
            ([detect.Stream(4100, "chrome", "Google Chrome input", "running", False, True)], [window("Meet - abc-defg-hij - Google Chrome")]),
            ([detect.Stream(4100, "chrome", "Google Chrome input", "running", False, True)], [window("Inbox - Google Chrome")]),
            ([detect.Stream(900, "voicechat", "Voice", "running", False, True)], []),
            ([detect.Stream(5200, "zoom", "zoom", "idle", False, True)], []),
        ]
        for streams, clients in cases:
            self.assertIsNone(match(streams, clients))

    def test_monitor_stream_does_not_hide_a_real_stream(self):
        streams = [
            detect.Stream(900, "voicechat", "Voice", "running", True),
            detect.Stream(4100, "chrome", "Google Chrome input", "running"),
        ]
        found = match(streams, [window("Inbox - Google Chrome")])
        self.assertEqual(found.app, "Google Chrome")

    def test_stream_from_audio_utility_child_resolves_to_browser_window(self):
        streams = [detect.Stream(2445056, "chrome", "Google Chrome input", "running")]
        ppid = parents({2445056: 544746, 544746: 2242, 2242: 2014, 2014: 1})
        clients = [
            window("Mail - Google Chrome", address="0x1", pid=544746, focus=2),
            window("Meet - abc-defg-hij - Google Chrome", address="0x2", pid=544746, focus=1),
        ]
        found = match(streams, clients, ppid=ppid)
        self.assertEqual((found.app, found.window.address), ("Google Meet", "0x2"))

    def test_ancestor_window_resolves_native_app_window(self):
        streams = [detect.Stream(5201, "zoom", "ZOOM VoiceEngine", "running")]
        clients = [
            window("Other", cls="other", pid=99, address="0x1"),
            window("Zoom Meeting", cls="zoom", pid=5200, address="0x2"),
        ]
        found = match(streams, clients, ppid=parents({5201: 5200}))
        self.assertEqual(found.window.address, "0x2")

    def test_ancestor_window_resolves_generic_native_app(self):
        streams = [detect.Stream(901, "/bin/helper", "Helper", "running")]
        clients = [window("Room", cls="voiceclass", pid=900)]
        found = match(streams, clients, ppid=parents({901: 900}))
        self.assertEqual((found.app, found.title), ("voiceclass", "Room"))

    def test_ancestor_window_matches_slack_huddle(self):
        streams = [detect.Stream(6101, "slack", "Slack", "running")]
        clients = [detect.Client("0x1", "app", "Huddle with Sam", 6100, (0, 0), (1, 1))]
        found = match(streams, clients, ppid=parents({6101: 6100}))
        self.assertEqual(found.window.address, "0x1")

    def test_ignore_apps_sees_window_class_of_ancestor(self):
        streams = [detect.Stream(901, "/bin/helper", "Helper", "running")]
        clients = [window("Room", cls="voiceclass", pid=900)]
        self.assertIsNone(match(streams, clients, ignore_apps=["voiceclass"], ppid=parents({901: 900})))

    def test_unrelated_window_pid_is_not_own_without_ancestry(self):
        streams = [detect.Stream(2445056, "chrome", "Google Chrome input", "running")]
        clients = [
            window("Mail - Google Chrome", address="0x1", pid=544746, focus=2),
            window("News - Google Chrome", address="0x2", pid=544746, focus=0),
        ]
        self.assertEqual(match(streams, clients).window.address, "0x2")

    def test_recorders_never_match(self):
        self.assertIsNone(candidate("recorders"))

    def test_ignored_pids(self):
        self.assertIsNone(candidate("zoom", ignore_pids=[5200]))
        self.assertIsNone(candidate("meet", ignore_pids={4100}))


class LineageTest(unittest.TestCase):
    def test_chain_follows_parents_and_stops_at_init(self):
        ppid = parents({30: 20, 20: 10, 10: 1})
        self.assertEqual(detect.lineage(30, ppid), (30, 20, 10))

    def test_chain_tolerates_missing_entries(self):
        self.assertEqual(detect.lineage(30, no_parent), (30,))
        self.assertEqual(detect.lineage(30, parents({30: 20})), (30, 20))
        self.assertEqual(detect.lineage(None, no_parent), ())

    def test_chain_is_bounded_and_cycle_safe(self):
        endless = lambda pid: pid + 1
        self.assertEqual(len(detect.lineage(100, endless, depth=3)), 4)
        self.assertEqual(len(detect.lineage(100, endless)), detect.MAX_ANCESTORS + 1)
        self.assertEqual(detect.lineage(5, parents({5: 6, 6: 5})), (5, 6))

    def test_read_ppid_parses_stat_with_odd_command_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            for pid, text in [(10, "10 (chrome) S 7 10 10 0 -1"), (11, "11 (a b) c) S 9 1 1")]:
                (Path(tmp) / str(pid)).mkdir()
                (Path(tmp) / str(pid) / "stat").write_text(text)
            (Path(tmp) / "12").mkdir()
            (Path(tmp) / "12" / "stat").write_text("garbage")
            self.assertEqual(detect.read_ppid(10, tmp), 7)
            self.assertEqual(detect.read_ppid(11, tmp), 9)
            self.assertIsNone(detect.read_ppid(12, tmp))
            self.assertIsNone(detect.read_ppid(13, tmp))


class DetectorTest(unittest.TestCase):
    def test_meet_sequence(self):
        detector = detect.Detector()
        names = ["idle", "meet", "meet", "meet", "idle", "idle", "idle", "idle", "idle", "idle"]
        events = run_sequence(detector, names)
        self.assertEqual([(i, e.kind) for i, e in events], [(2, "start"), (8, "end")])
        start = events[0][1]
        self.assertEqual(start.app, "Google Meet")
        self.assertEqual(start.title, "Meet - abc-defg-hij - Google Chrome")
        self.assertEqual(start.window.address, "0x5600b7")
        self.assertEqual(start.at, at(5))
        end = events[1][1]
        self.assertEqual(end.app, "Google Meet")
        self.assertEqual(end.at, at(20))
        self.assertEqual(at(40) - end.at, timedelta(seconds=20))

    def test_brief_absence_does_not_end(self):
        detector = detect.Detector()
        names = ["meet", "meet", "idle", "idle", "idle", "meet", "meet", "idle"]
        events = run_sequence(detector, names)
        self.assertEqual([e.kind for _, e in events], ["start"])
        self.assertIsNotNone(detector.active)

    def test_single_positive_poll_does_not_start(self):
        detector = detect.Detector()
        events = run_sequence(detector, ["idle", "meet", "idle", "meet", "idle"])
        self.assertEqual(events, [])

    def test_recorders_and_chrome_alone_never_trigger(self):
        detector = detect.Detector()
        names = ["recorders"] * 6 + ["idle"] * 6
        self.assertEqual(run_sequence(detector, names), [])

    def test_whatsapp_web_call_starts_a_meeting(self):
        detector = detect.Detector()
        events = run_sequence(detector, ["idle", "chrome_no_meet", "chrome_no_meet"])
        self.assertEqual([(i, e.kind, e.app) for i, e in events], [(2, "start", "Google Chrome")])

    def test_manual_mode_ignores_detector(self):
        detector = detect.Detector()
        started = detector.force_start("Manual", "Standup", at(0))
        self.assertEqual([e.kind for e in started], ["start"])
        self.assertEqual((started[0].app, started[0].title, started[0].at), ("Manual", "Standup", at(0)))
        for second in range(5, 120, 5):
            self.assertEqual(detector.feed(at(second), None), [])
        for second in range(120, 140, 5):
            self.assertEqual(detector.feed(at(second), candidate("zoom")), [])
        stopped = detector.force_stop(at(140))
        self.assertEqual([(e.kind, e.app, e.at) for e in stopped], [("end", "Manual", at(140))])
        self.assertIsNone(detector.active)

    def test_force_start_adopts_running_meeting(self):
        detector = detect.Detector()
        run_sequence(detector, ["meet", "meet"])
        self.assertEqual(detector.force_start("Manual", "Standup", at(10)), [])
        self.assertTrue(detector.manual)
        for second in range(15, 100, 5):
            self.assertEqual(detector.feed(at(second), None), [])
        stopped = detector.force_stop(at(100))
        self.assertEqual([(e.kind, e.app) for e in stopped], [("end", "Google Meet")])

    def test_force_stop_of_detected_meeting_waits_for_mic_to_drop(self):
        detector = detect.Detector()
        run_sequence(detector, ["meet", "meet"])
        self.assertEqual([e.kind for e in detector.force_stop(at(10))], ["end"])
        meet = candidate("meet")
        for second in range(15, 60, 5):
            self.assertEqual(detector.feed(at(second), meet), [])
        self.assertEqual(detector.feed(at(60), None), [])
        detector.feed(at(65), meet)
        self.assertEqual([e.kind for e in detector.feed(at(70), meet)], ["start"])

    def test_generic_meeting_is_capped_at_four_hours(self):
        detector = detect.Detector()
        generic = detect.Candidate("Voice", "Voice", None, True)
        self.assertEqual(detector.feed(at(0), generic), [])
        self.assertEqual([e.kind for e in detector.feed(at(5), generic)], ["start"])
        for second in range(10, 4 * 3600, 600):
            self.assertEqual(detector.feed(at(second), generic), [])
        ended = detector.feed(at(5 + 4 * 3600), generic)
        self.assertEqual([(e.kind, e.app, e.at) for e in ended], [("end", "Voice", at(5 + 4 * 3600))])
        self.assertIsNone(detector.active)

    def test_capped_generic_meeting_does_not_restart_until_stream_goes_away(self):
        detector = detect.Detector()
        generic = detect.Candidate("Voice", "Voice", None, True)
        detector.feed(at(0), generic)
        detector.feed(at(5), generic)
        base = 5 + 4 * 3600
        detector.feed(at(base), generic)
        for step in range(5, 200, 5):
            self.assertEqual(detector.feed(at(base + step), generic), [])
        self.assertIsNone(detector.active)
        detector.feed(at(base + 200), None)
        detector.feed(at(base + 205), generic)
        self.assertEqual([e.kind for e in detector.feed(at(base + 210), generic)], ["start"])

    def test_capped_app_does_not_block_specific_meeting(self):
        detector = detect.Detector()
        generic = detect.Candidate("Voice", "Voice", None, True)
        zoom = detect.Candidate("Zoom", "Zoom Meeting", None)
        detector.feed(at(0), generic)
        detector.feed(at(5), generic)
        detector.feed(at(5 + 4 * 3600), generic)
        base = 5 + 4 * 3600
        detector.feed(at(base + 5), zoom)
        self.assertEqual([e.kind for e in detector.feed(at(base + 10), zoom)], ["start"])

    def test_specific_meeting_is_not_capped(self):
        detector = detect.Detector()
        zoom = detect.Candidate("Zoom", "Zoom Meeting", None)
        detector.feed(at(0), zoom)
        detector.feed(at(5), zoom)
        for second in range(10, 6 * 3600, 900):
            self.assertEqual(detector.feed(at(second), zoom), [])
        self.assertIsNotNone(detector.active)

    def test_manual_meeting_is_not_capped(self):
        detector = detect.Detector()
        detector.force_start("Manual", "Standup", at(0))
        self.assertEqual(detector.feed(at(5 * 3600), None), [])
        self.assertIsNotNone(detector.active)

    def test_force_stop_without_meeting(self):
        self.assertEqual(detect.Detector().force_stop(at(0)), [])


class FakeRun:
    def __init__(self, outputs, fail=()):
        self.outputs = outputs
        self.fail = set(fail)
        self.calls = []

    def __call__(self, argv, env=None):
        self.calls.append((list(argv), env))
        if argv[0] in self.fail:
            raise subprocess.CalledProcessError(1, argv)
        return self.outputs[argv[0]]


class SnapshotTest(unittest.TestCase):
    def outputs(self):
        data = fixture("meet")
        return {"pw-dump": json.dumps(data["pw_dump"]), "hyprctl": json.dumps(data["clients"])}

    def test_snapshot_with_signature(self):
        run = FakeRun(self.outputs())
        environ = {"HYPRLAND_INSTANCE_SIGNATURE": "sig", "XDG_RUNTIME_DIR": "/nonexistent"}
        streams, clients = detect.snapshot(run, environ)
        self.assertEqual(streams[0].binary, "chrome")
        self.assertEqual(clients[1].pid, 4100)
        self.assertEqual(run.calls[0][0], ["pw-dump"])
        self.assertEqual(run.calls[1][0], ["hyprctl", "clients", "-j"])
        self.assertEqual(run.calls[1][1]["HYPRLAND_INSTANCE_SIGNATURE"], "sig")

    def test_snapshot_finds_newest_hyprland_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            hypr = Path(tmp) / "hypr"
            for name, mtime in [("old", 1000), ("new", 2000), ("mid", 1500)]:
                (hypr / name).mkdir(parents=True)
                os.utime(hypr / name, (mtime, mtime))
            run = FakeRun(self.outputs())
            result = detect.snapshot(run, {"XDG_RUNTIME_DIR": tmp})
            self.assertIsNotNone(result)
            self.assertEqual(run.calls[1][1]["HYPRLAND_INSTANCE_SIGNATURE"], "new")

    def test_snapshot_failure_returns_none(self):
        environ = {"HYPRLAND_INSTANCE_SIGNATURE": "sig"}
        self.assertIsNone(detect.snapshot(FakeRun(self.outputs(), fail=["pw-dump"]), environ))
        self.assertIsNone(detect.snapshot(FakeRun(self.outputs(), fail=["hyprctl"]), environ))
        broken = FakeRun({"pw-dump": "not json", "hyprctl": "[]"})
        self.assertIsNone(detect.snapshot(broken, environ))

        def missing(argv, env=None):
            raise FileNotFoundError(argv[0])

        self.assertIsNone(detect.snapshot(missing, environ))

    def test_snapshot_without_any_hyprland_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = FakeRun(self.outputs())
            self.assertIsNone(detect.snapshot(run, {"XDG_RUNTIME_DIR": tmp}))


if __name__ == "__main__":
    unittest.main()
