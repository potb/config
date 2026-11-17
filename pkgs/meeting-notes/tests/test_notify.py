import unittest
from types import SimpleNamespace

from meeting_notes import notify


class Recorder:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, argv):
        self.calls.append(argv)
        if self.error:
            raise self.error
        return SimpleNamespace(returncode=0, stderr="")


class NotifyTest(unittest.TestCase):
    def test_linux(self):
        run = Recorder()
        notify.send("Titre", "Corps", run, "linux")
        self.assertEqual(run.calls, [["notify-send", "-a", "meeting-notes", "Titre", "Corps"]])

    def test_darwin_escapes_quotes(self):
        run = Recorder()
        notify.send('Say "hi"', 'a\\b "c"', run, "darwin")
        self.assertEqual(
            run.calls,
            [["osascript", "-e", 'display notification "a\\\\b \\"c\\"" with title "Say \\"hi\\""']],
        )

    def test_failure_swallowed_and_logged(self):
        run = Recorder(error=FileNotFoundError("notify-send"))
        with self.assertLogs("meeting_notes.notify", level="WARNING"):
            notify.send("t", "b", run, "linux")

    def test_nonzero_exit_swallowed(self):
        def run(argv):
            return SimpleNamespace(returncode=1, stderr="nope")

        with self.assertLogs("meeting_notes.notify", level="WARNING"):
            notify.send("t", "b", run, "linux")
