# meeting-notes

meeting-notes detects calls, records both sides of the audio, transcribes it
locally and has Claude write notes and a corrected transcript. The package is
`pkgs/meeting-notes`, the options and services are in
`modules/dev/meeting-notes.nix`, and each host sets its values in
`hosts/<host>/modules/meeting-notes.nix`.

One user service, `meeting-notes watch`, does everything. Claude runs headless
from it. Nothing is sent to Slack or anywhere else.

## Hosts

| Host | Backend | Model | Live | Status |
|------|---------|-------|------|--------|
| `charon` | native | `large-v3` | on | built, not yet activated |
| `kerberos` | native | `large-v3-turbo` | off | NOT TESTED |
| `nyx` | screenpipe | `large-v3` | off | NOT TESTED |

charon is the reference host, and its system closure builds. kerberos uses the
same code with a smaller model and no live pass. Its configuration only
evaluates: it has never been built, and nobody has recorded a call on it. nyx
is untested too: `darwin` only evaluates, it has never been built or activated.

On charon and kerberos the watcher is a systemd user unit, started with the
graphical session and restarted after 10 s on exit. On nyx it is a launchd
agent, and a second agent runs `meeting-notes screenpipe`, which starts
`screenpipe record --port 3030 --disable-telemetry -a disabled`. The
`-a disabled` flag turns off screenpipe's own audio capture. The watcher turns
audio on and off through the screenpipe API for the length of a meeting.

charon still runs the older service from `hosts/charon/modules/screenpipe.nix`.
The native backend does not use it.

## Why not Screenpipe on Linux

The spike of 2026-11-17 on screenpipe 0.4.58 found two blockers. Google Meet
in Chrome is not detected as a meeting, and there is no flag that records
meetings only. Screenpipe would capture everything, all day. Linux therefore
uses the native backend. macOS has no PipeWire, so nyx keeps screenpipe.

## The screenpipe package

`pkgs/screenpipe/package.nix` repackages the prebuilt CLI from npm for two
platforms. Each platform has its own flake input, and
`overlays/custom-packages.nix` picks one:

- `screenpipe-cli`: `@screenpipe/cli-linux-x64`, latest. On Linux
  `autoPatchelfHook` patches the binary, and the wrapper puts `ffmpeg`, `grim`
  and `hyprland` on its `PATH`.
- `screenpipe-cli-darwin`: `@screenpipe/cli-darwin-arm64`, pinned to 0.4.58.
  No patching. The wrapper adds only `ffmpeg`.

`meta.platforms` is `x86_64-linux` and `aarch64-darwin`. The darwin build has
never been run, so treat the nyx package as unverified.

## Detection (native)

The watcher polls every 5 s with the native backend. With the screenpipe
backend (nyx) it polls the screenpipe API every 10 s instead. On each native
poll it reads two things:

- `pw-dump`: streams of class `Stream/Input/Audio` in state `running` or
  `idle`. A stream is a microphone being read.
- `hyprctl` window titles, to name the call.

Streams from `ffmpeg` and `screenpipe` are ignored, so the recorder never
detects itself.

The order is Slack first (a window titled "Huddle"), then Zoom, WhatsApp,
Discord, Teams and Jitsi, then browsers. A Chrome, Chromium or Firefox window
titled `Meet - ...` with an open microphone counts as Meet. Slack comes first
because Electron apps can show up as "Chromium input".

Two polls with a microphone start a meeting. The meeting ends once the
microphone has been gone for 20 s. A poll that fails neither starts nor ends
anything.

## Recording (native)

On start the watcher launches two `ffmpeg` processes with `-f pulse`: the
default source (the microphone, side `me`) and the monitor of the default sink
(system audio, side `others`). If `pactl get-default-sink` fails, only the
microphone is recorded.

Audio is 16 kHz mono AAC, cut into 30 s chunks. Chunk names copy Screenpipe's:
`<device> (input|output)_%Y-%m-%d_%H-%M-%S.mp4`, in UTC. They go to
`~/.local/share/meeting-notes/audio`.

`grim -T <stableId>` captures the call window at the start and then every 5
minutes while the window still exists. The PNGs land in `work/<id>/screens/`
and Claude reads them to name the participants, so they are sent to Anthropic
with the transcript.

The capture targets the window itself through Hyprland's
`ext-foreign-toplevel-image-capture` protocol, using the `stableId` from
`hyprctl clients -j` as the toplevel identifier. It shows the call window even
when it is covered or on another workspace, and never what sits on top of it.
A region capture (`grim -g`) would grab whatever is drawn at the window's
position, such as a banking tab covering the call, so there is no fallback to
it: a window without a `stableId` gets no screenshot. Chrome may stop redrawing
a hidden window, in which case the capture shows its last frame, which is
still enough for the names.

## Transcription

`whisper-cli` (Vulkan build on Linux) transcribes each chunk on its own:

- A `volumedetect` pass skips chunks that are silent, below -50 dB peak.
- `ffmpeg` filters the audio first: high-pass at 80 Hz and `loudnorm`.
- whisper runs with the Silero VAD model, beam size 8, and a prompt built from
  `glossary.md`. The prompt is French when `language` is `fr`, English otherwise.
- A chunk with fewer than 6 words that is not quiet gets one retry without the
  prompt. The longer result wins.
- Known hallucinations such as "thanks for watching" are dropped.
- Results are cached by chunk name, model and cache version in
  `work/asr-cache`. Each write goes through its own temporary file, so the
  live pass and the fetch can write the same entry at once.
- A chunk that ffmpeg cannot read at all, for example a truncated `mp4` after a
  crash, is skipped. The fetch still finishes, and `meta.json` lists the
  skipped chunks under `skipped_chunks`. Any other failure, such as whisper
  running out of memory or the prefilter failing, fails the fetch, so the
  watcher counts an attempt and retries it later.
- A meeting takes the chunks from 35 s before its start to its end, but never a
  chunk that starts before the previous meeting ended. Cleanup uses the same
  window.

Live passes run whisper and ffmpeg under `ionice -c3 nice -n19`. On macOS they
run under `taskpolicy -b`. The final fetch runs at normal priority.

With `live = true` the watcher transcribes complete chunks every 20 s during
the call, so `fetch` only has the tail left. If two live passes in a row have a
chunk that takes more than 10 s, the live pass stops for that meeting and
`state.json` shows `live` as `stopped_slow`. The final fetch then does the
rest. One slow pass is tolerated because the first chunk of a call reads the
3 GB model from disk at idle IO priority: on charon that chunk took over 10 s
while a warm chunk takes about 3 s.

## Claude run

60 s after a meeting ends, a single worker runs `meeting-notes fetch <id>`,
then one headless Claude. Fetch has a 3 h timeout and Claude has 1 h. A
catch-up scan every 15 min picks up meetings that were missed.

Claude runs only when at least one meeting is ready: fetched, or with its notes
already saved. Each failed fetch counts as one attempt for that meeting, and so
does a Claude run that leaves one of the three oldest ready meetings
unfinished. `meeting-notes pending` lists only ready meetings, so the three
meetings Claude takes are exactly the three the watcher counts. `state.json` keeps `attempts` and `last_error` under `processed`.
After 3 attempts the meeting becomes `failed`, which is final: no more retries,
and cleanup treats it like a finished meeting. To retry it, delete its
`processed` entry.

Claude starts in `~/.local/share/meeting-notes` with
`-p <prompt> --permission-mode acceptEdits` and `--add-dir` on `~/Meetings`.
The allowed tools are:

- `Bash(meeting-notes pending)`
- `Bash(meeting-notes finish:*)`
- `Read`, `Write`, `Edit`, `Glob`, `Grep`

The prompt names the owner, tells Claude to follow `pipe.md` and use
`glossary.md`, forbids sending anything and forbids reading `.env`. Claude
never fetches or transcribes. If `work/<id>/fetched.ok` is missing, it leaves
the meeting for the next run.

`meeting-notes finish` records the result in `state.json`: notes saved first,
transcript second, or a skip with a reason. `pipe.md` tells Claude to write
notes into `meetings/YYYY-MM-DD-<slug>/`, relative to the data directory.

`--skip` and `--sensitive` take an optional reason, stored as `skip_reason`
and `sensitive`. An empty or blank reason counts as the bare flag. A sensitive
meeting is never posted to Slack, even with
`slack.enable`. The flag set at the notes stage also holds for the transcript
stage. `finish` refuses `--notes` and `--transcript` paths outside
`meetings/` in the data directory and `~/Meetings`, so Claude cannot use it to
read or copy other files.

## Options

Set under `services.meeting-notes`, which the `dev` module declares for NixOS
and nix-darwin.

| Option | Default | charon | kerberos | nyx |
|--------|---------|--------|----------|-----|
| `owner` | `Peïo` | default | default | default |
| `backend` | `native` | `native` | `native` | `screenpipe` |
| `model` | `large-v3` | `large-v3` | `large-v3-turbo` | `large-v3` |
| `live` | `false` | `true` | `false` | `false` |
| `language` | `fr` | default | default | default |
| `retentionDays` | `7` | default | default | default |
| `minMinutes` | `5` | default | default | default |
| `slack.enable` | `false` | default | default | default |

`minMinutes` is the shortest meeting that gets notes. `owner` names the person
on the microphone side.

The module turns each option into a `MEETING_NOTES_*` variable on the service.
The VAD model, whisper, ffmpeg and the claude path (from the per-user profile)
come from the Nix store, not from options.

## State files

Everything lives in `~/.local/share/meeting-notes`:

| Path | Content |
|------|---------|
| `state.json` | meetings and their status, written under a file lock |
| `control/` | `start.json` and `stop`, the manual start and stop requests |
| `work/<id>/` | `meta.json`, `transcript.txt`, `screen.txt`, `screens/`, `fetched.ok` |
| `work/asr-cache/` | cached chunk transcriptions |
| `runs/` | one log per Claude run and per fetch |
| `audio/` | native backend chunks |
| `screenpipe.key` | API key for the local screenpipe server, mode 600 |
| `pipe.md`, `glossary.md` | read-only links into the package, see below |

The screenpipe backend keeps its audio in `~/.screenpipe/data`. The key is
created on first use and never printed. `meeting-notes check` only reports that
it exists.

## Editing pipe.md and glossary.md

The package installs both files to `share/meeting-notes`, and the module
links them from there into the data directory. The links point into the Nix
store, which is read-only. Claude has `Write` and `Edit` and reads transcripts
that other people speak into, so a prompt injected in a call could otherwise
rewrite its own instructions for every later run.

To change either file, edit it in `pkgs/meeting-notes/` and rebuild. The build
fails if one of them is missing.

## Checking a run

```bash
journalctl --user -u meeting-notes -f
meeting-notes status
meeting-notes check
```

- `status` shows the active meeting, `live`, the last pending check and the
  five latest results. `--json` gives the same as JSON.
- `state.json` has the full record, including `processed`.
- `work/<id>/fetched.ok` exists once transcription finished.
- `runs/*.log` hold the output of each Claude run and each fetch. A fetch log
  has `-fetch-` in its name.
- `check` lists the required tools, the models, the backend, the paths and
  returns 1 if anything is missing.

On nyx the watcher writes to `watch.log` and the screenpipe agent to
`screenpipe.log`, both in the data directory.

## Manual start and stop

```bash
meeting-notes start --title "Call with Bastien"
meeting-notes stop
```

Both write a file in `control/` that the watcher picks up on its next poll.
`--app` sets the app name, `Manual` by default. After a manual stop, automatic
detection stays off until the microphone has closed once. A manual start during
a meeting the native backend already detected changes nothing: the meeting
stays `auto`, and so does the next one.

## Stopping the watcher

When the watcher stops (logout, reboot, `systemctl --user stop`), it ends the
current meeting at that moment. After a crash or power loss the meeting is
still open in `state.json`. On the next start the watcher ends it at the
modification time of its last audio chunk, or at its start if it has no chunk,
never at the restart time.

## Notifications

During a meeting the watcher checks the newest chunk of each side. If one side
has had no new audio for 90 s, it sends one desktop notification, "No audio
from ... for 90 s", and one more, "Recording audio is back", when audio
returns. Linux uses `notify-send`, which is why the module puts `libnotify` on
the service `PATH`. macOS uses `osascript`.

## Retention

`meeting-notes cleanup` runs every hour from the watcher. For a finished
meeting older than `retentionDays` (7 by default) it deletes the audio chunks
of the native backend, the screenshots, the WAV files and the cache entries.
`work/<id>/` text files, `state.json` and the notes stay.

`~/Meetings` is never cleaned. Audio is not deleted if the audio directory sits
inside it. The screenpipe backend's audio in `~/.screenpipe/data` is left to
screenpipe.

## Slack

The code for a Slack post exists and `slack.enable` turns it on. It is off by
default and has never been exercised against a real workspace. Treat it as
unverified. The prompt tells Claude not to send anything while it is off.

## Known limits

- Without headphones the microphone records the speakers. `pipe.md` has Claude
  remove the echo from the transcript, which costs accuracy.
- A call where you only listen is not detected on Linux. Detection needs an
  open microphone, and that stream never exists. Use `meeting-notes start`.
- Changing the default sink during a call. The monitor source is fixed at
  start, so audio from the new sink is missed.
- With `live = true` whisper competes with games and the compositor for the
  GPU, despite `nice` and `ionice`, which do not govern the GPU.
- On macOS, TCC permissions are tied to the path of the screenpipe binary in
  the Nix store. A new store path after an update asks again.
- kerberos and nyx have not been run. Expect fixes on first use.
