# meeting-notes

meeting-notes detects calls, records both sides of the audio, transcribes it
locally and has Claude write notes and a corrected transcript. The package is
`pkgs/meeting-notes`, the options and services are in
`modules/dev/meeting-notes.nix`, and each host sets its values in
`hosts/<host>/modules/meeting-notes.nix`.

One user service, `meeting-notes watch`, does everything. Claude runs headless
from it. Nothing is sent to Slack or anywhere else unless `slack.enable` is
set, see [Slack](#slack).

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
  `idle`. A stream is a microphone being read. Streams with
  `stream.capture.sink` (a capture of an output sink, such as a monitor) and
  streams with `node.passive` are dropped before any rule runs.
- `hyprctl clients -j`: window class, title, pid and `focusHistoryID`, to name
  the call and pick the window to screenshot.

Chrome opens the microphone from an audio utility child process, so the stream
pid is not the pid Hyprland reports for the window. The watcher reads
`/proc/<pid>/stat` to follow the stream pid up its parent chain (at most 8
steps, stopping at pid 1 or an unreadable entry). A window belongs to the
stream when its pid is the stream pid or any ancestor. A window class from that
chain is also what `ignoreApps` sees.

Any window or app that takes the microphone starts a meeting. Specific rules
come first and keep their labels, then labelled web apps, then generic
candidates. Within each step the first matching stream wins:

1. Slack (a window titled "Huddle"), then Zoom, WhatsApp, Discord, Teams and
   Jitsi native binaries, then a Chrome, Chromium or Firefox window titled
   `Meet - ...`. Slack comes first because Electron apps can show up as
   "Chromium input". These match a stream in state `running` or `idle`. The
   Google Meet home page, titled `Google Meet - ...`, is not a meeting.
2. A browser holding a `running` microphone stream with no `Meet - ...` window:
   the first window of that browser, the stream's own windows first and then
   the most recently focused, whose title (without the browser suffix) matches
   a web call app. The label is that app name. The patterns are anchored to how
   each app titles its tabs, so a document titled "Q3 teams planning" does not
   match:

   | App | Tab title |
   | --- | --- |
   | WhatsApp | starts with `WhatsApp` or `(N) WhatsApp` |
   | Teams | contains `\| Microsoft Teams` |
   | Zoom | exactly `Zoom Meeting` or `Zoom Workplace`, or starts with `app.zoom.us` |
   | Discord | starts with `Discord` or ends with `- Discord` |
   | Jitsi | is or ends with `Jitsi Meet` (`room \| Jitsi Meet`) |
   | Whereby | is or ends with `Whereby` (`room - Whereby`) |
   | Webex | is or ends with `Webex`, `Cisco Webex` or `Webex Meetings` |

3. Generic fallback, only for a `running` stream. A browser with no known title
   becomes an app named after the browser (`Google Chrome`, `Chromium` or
   `Firefox`), so screenpipe screen-context filters can match it. Its title and
   screenshot window come from the stream's own windows if any, else the most
   recently focused window of that browser class (`focusHistoryID` 0 is the
   focused one). With several windows and no way to tell which tab holds the
   call, the screenshot target may be the wrong window. Any other binary
   becomes an app named after the class of its window, else the stream's
   `application.name`, else the binary name, titled by that window or the app
   name.

An `idle` stream (a microphone that is open but carries no audio) only matches
step 1, so a Meet tab, Slack huddle or native Zoom/WhatsApp/Discord/Teams/Jitsi
app keeps its meeting while muted or silent. Steps 2 and 3 need a `running`
stream, so a web-app or generic meeting whose stream goes `idle` ends after the
20 s grace.

A meeting started by step 3 (generic) ends after 4 hours as a safety cap, in
case a stream that never closes holds the microphone. The same app is not
started again until a poll sees no candidate at all. A specific candidate from
step 1 or 2 still starts a meeting meanwhile. Meetings from steps 1 and 2 and
manual meetings have no cap.

These are never detected, so the recorder and mic tools do not detect
themselves: `ffmpeg`, `screenpipe`, `pw-record`, `pw-cat`, `parecord`, `parec`,
`arecord`, `rec`, `sox`, anything starting with `whisper`, and `meeting-notes`
itself. Add more with `ignoreApps`. Each entry is matched case-insensitively
as a substring against the binary name, `application.name` and the window class
of the stream's pid or its ancestors, and it applies to every rule. Because it
is a substring match, `obs` also ignores `obsidian`: use a specific name such
as `com.obsproject.Studio` or `obs-studio`, and check the window class with
`hyprctl clients -j`. The service reads the list from
`MEETING_NOTES_IGNORE_APPS`, comma separated.

Generic detection can trigger on dictation or a voice note. The existing
filters handle those: a meeting shorter than `minMinutes` gets no notes, and
`pipe.md` skips a call that is one-sided or has fewer than 80 words after echo
removal. Use `ignoreApps` for an app that keeps tripping detection.

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
minutes while the window still exists. The PNGs land in `work/<id>/screens/`.

At fetch, tesseract (`ocrLanguages`, English and French by default) reads each
capture under `nice -n 10`, about 2 s for a Meet window. `screen.txt` gets one
`## <capture>.png` heading per capture followed by the lines not already seen in
an earlier capture, so a static grid of tiles costs its text once. A capture the
OCR cannot read keeps its heading with no text. Claude names the participants
from `screen.txt` and `meta.json` only: the OCR text is a few thousand tokens
per meeting where the images would cost about 2,000 tokens each, and the PNGs
never leave the machine. The prompt forbids opening them, and the run passes
`--disallowedTools` with `Read(**/*.png)`, `Read(**/*.jpg)`, `Read(**/.env)`,
`Read(**/voices/**)` and `Read(**/*.npz)`, so a Read on a capture, on the token
file or on voice data is refused even if the model tries. Whatever Claude reads is sent to Anthropic with the
transcript.

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

## Diarization and voice prints

Whisper only knows two sides: `me` (the microphone) and `others` (system audio). In a
call with several other people, `others` mixes them all. Diarization splits the
`others` track into voices, on the CPU, without any network access. Audio never leaves
the machine.

### What it does

Once per meeting, at fetch, `meeting-notes fetch` starts `meeting-notes diarize <id>`
as a subprocess. It never runs per chunk and never during live transcription.

1. It takes the meeting's `others` chunks (the same window and floor as
   transcription), decodes each with `ffmpeg` to 16 kHz mono and concatenates them
   in time order. A gap of more than 1.5 s between the end of one chunk and the start
   of the next is filled with silence, so track time stays aligned with the clock. A
   chunk ffmpeg cannot read (a crash leaves one without its `moov` atom) is skipped
   and listed under `skipped_chunks`. The chunk-to-offset map is kept.
2. Silero VAD (ONNX) finds the speech regions.
3. Windows of 1.5 s with a 0.75 s hop over the speech go through WeSpeaker ResNet34
   (VoxCeleb, ONNX): 80-bin kaldi fbank with mean normalisation, one 256-d embedding
   per window.
4. Spectral clustering on the window cosine affinities (k nearest neighbours, 10 %),
   with the speaker count picked by the largest eigengap of the normalised Laplacian,
   1 to 6 speakers. Above 6,000 windows (about 75 min of speech) a uniform sample of
   6,000 is clustered and the other windows join the nearest centroid.
5. Each 50 ms frame takes the cluster whose centroid best matches the windows over
   it, a 9-frame median filter removes flicker, and runs of frames become turns.
6. Clusters are named `S1`, `S2`... by talk time, then matched against the voice
   prints (below).

Back in `fetch`, each whisper segment of the `others` side gets the cluster that
overlaps it most. The ASR cache only stores segment starts, so a segment ends at the
next segment's start in the same chunk, or at the end of the chunk. Lines then read
`others:Bastien` when a print matched, `others:S2` otherwise. Microphone lines stay
`me`. A segment outside every turn, or from a chunk the diarizer skipped, stays plain
`others`.

The pipeline is a port of the prototype validated on two real calls of 2026-11-18
(Mazmez and Jamrock, 44 and 43 min, three other participants each). Against the
corrected transcripts it agreed on about 93 % of the words, and the owner confirmed
by ear 14 clips out of 14.

### CPU policy

- The subprocess runs under `ionice -c3 nice -n19` (`taskpolicy -b` on macOS).
- onnxruntime uses the CPU provider only, with `diarization.threads` intra-op threads
  (4 by default) and one inter-op thread. `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`
  and `MKL_NUM_THREADS` get the same value, so the eigendecomposition does not take
  every core either.
- On charon a 44 min call took about 45 s wall time and 3 to 4 CPU minutes at 4
  threads, with a peak around 900 MB of memory.
- If another meeting is active when a meeting is due for fetch, the watcher defers its
  fetch, and with it the diarization and the notes, until no meeting is active. It
  logs `deferring fetch and diarization of <id> while meeting <other> is active` at
  each check. After `diarization.maxDelayMinutes` (180 by default) counted from the
  end of the meeting, it fetches anyway, still at low priority. Without diarization
  (disabled, or models missing) nothing is deferred.
- The subprocess has a 1 h timeout.

### Failure never blocks the notes

Missing models, a crash, a timeout, an unreadable result, or less than 2 minutes of
speech on the `others` track: `fetch` logs the reason, writes it to `speakers.json`
and to `diarization` in `meta.json`, and keeps today's plain `others` lines. The fetch
itself succeeds.

### Files

| Path | Content |
|------|---------|
| `work/<id>/speakers.json` | `status`; per cluster: `id` (`S1`...), talk `seconds`, matched `name` or `null`, `cosine` and `margin` against the prints, `turns` in track seconds; the chunk map (`chunks`: name, start, offset, seconds); `skipped_chunks`; timing |
| `work/<id>/speakers.npz` | window embeddings, windows and cluster of each window, kept for `voices add` |
| `voices/<slug>.json` | one voice print: `name`, 256-d `vector`, `seconds`, source `meetings`, `confirmed_at` |

`voices/` is created with mode 700. `meta.json` gets `diarization`: `status` (`ok`,
`skipped`, `failed`), the reason, the speaker count and the names matched.

### Voice prints

A print is the L2-normalised mean of the L2-normalised window embeddings of one
person. Prints are only made by the owner, with an explicit command, never
automatically:

```bash
meeting-notes voices list
meeting-notes voices add --id 20261118-104545 --speaker S3 --name Quentin
meeting-notes voices remove --name Quentin
meeting-notes voices import --name Bastien --file prints.npz --key Bastien
```

- `add` reads `speakers.json` and `speakers.npz` of that meeting, takes the windows of
  that cluster, and creates the print or updates it: the new vector is the mean of the
  old and the new one weighted by their seconds. A meeting already in the print is
  refused. Listen to a few lines (or read `transcript.txt`) before confirming a
  cluster: a wrong print mislabels every later meeting.
- `import` seeds a print from an array in an `.npz` (`--key` is the array name) or a
  JSON file (`--key` at the top level or under `prints`), with optional `--seconds` and
  `--id`. It refuses a name that already has a print.
- `list` prints names, seconds, meetings and dates, never the vectors.

`speakers.npz` is deleted by cleanup after `retentionDays`, like the audio. After
that a meeting can no longer feed `voices add`.

### Matching rules

A cluster takes a print's name when the cosine between the cluster centroid and the
print is at least 0.6 and beats the second best print by at least 0.15 (with a single
print, by at least 0.15 above zero). Each print names at most one cluster per meeting:
when two clusters qualify for the same print, the higher cosine wins and the other
keeps its `S` label. Unmatched clusters keep `S<n>`.

The basis, measured on the two validation calls with prints built from the first: the
same person scored 0.98 between cluster and print, different people at most 0.43, and
a voice with no print 0.25. 0.6 sits well clear of both sides, and the 0.15 margin
keeps a near tie unnamed.

### What Claude does with the labels

`pipe.md` and the watcher's prompt say: `others:<Name>` comes from a confirmed print
and is reliable; `others:S<n>` are distinct unknown voices, each to be given one name
from `meta.json`, `screen.txt` and the content, the same through the meeting, with
`(?)` only when truly unsure; a short interjection may carry the wrong label.
`transcript.md` keeps its format (`**[HH:MM] Name :** text`) and never shows `S`
labels, so the Honcho export in `modules/agents/screenpipe-export/export.py` parses it
unchanged.

### Privacy

Voice prints and window embeddings are biometric data. They stay in the data
directory on this machine. They are never sent to Claude: the prompt and `pipe.md`
only mention the labels, and the run adds `Read(**/voices/**)` and `Read(**/*.npz)`
to `--disallowedTools`, plus `Write(**/voices/**)` and `Edit(**/voices/**)` so the
run cannot create or alter a print either. Prints change only through the `voices`
commands. With a single print the margin rule compares against zero, so the 0.6
cosine threshold alone decides; unknown voices measured at most 0.43. They are never posted to Slack, and never exported to Honcho: the export reads only
`notes.md` and `transcript.md`. `speakers.json` holds cosines and turns, no vectors.
Delete a print with `voices remove`.

### Models

`pkgs/meeting-notes/models.nix` fetches both with fixed hashes:

- `silero-vad-onnx`: `silero_vad.onnx` from `istupakov/silero-vad-onnx` on Hugging
  Face, pinned to a commit. The `silero-vad` entry next to it is the ggml build for
  whisper.cpp and cannot be read by onnxruntime.
- `wespeaker-resnet34`: `wespeaker_en_voxceleb_resnet34.onnx` from the sherpa-onnx
  `speaker-recongition-models` release (the tag is misspelled upstream).

The service gets them as `MEETING_NOTES_DIARIZATION_VAD_MODEL` and
`MEETING_NOTES_SPEAKER_MODEL`. The Python side uses onnxruntime, numpy, scipy and
kaldi-native-fbank from nixpkgs. `MEETING_NOTES_VOICES_DIR` overrides the prints
folder, for tests and trials.

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
`-p <prompt> --model <notesModel> --permission-mode acceptEdits` and
`--add-dir` on `~/Meetings`. `notesModel` defaults to `sonnet`, which is enough
to summarise a transcript; without it Claude would take the default model of
the owner's settings.
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
meeting is never posted to the Slack channel. With `slack.postTo = "dm"` it is
not posted at all, as before. With `slack.postTo = "channel"` it goes to the
owner's direct message only, header and files, never to the channel. The flag
set at the notes stage also holds for the transcript stage, including a
meeting whose notes already went to the channel: the transcript then gets its
own header and goes to the direct message, never into the channel thread (with
`postTo = "dm"` it is not posted). `finish` refuses `--notes` and `--transcript` paths outside
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
| `notesModel` | `sonnet` | default | default | default |
| `ocrLanguages` | `["eng" "fra"]` | default | default | default |
| `retentionDays` | `7` | default | default | default |
| `minMinutes` | `5` | default | default | default |
| `ignoreApps` | `[]` | default | default | default |
| `diarization.enable` | `true` on Linux | default | default | default (`false`) |
| `diarization.threads` | `4` | default | default | default |
| `diarization.maxDelayMinutes` | `180` | default | default | default |
| `slack.enable` | `false` | `false` | default | default |
| `slack.postTo` | `dm` | `dm` | default | default |
| `slack.channelId` | empty | `C0C23NA7EKX` | default | default |
| `slack.userId` | empty | `U0C228DMEV9` | default | default |

`minMinutes` is the shortest meeting that gets notes. `owner` names the person
on the microphone side. `ignoreApps` lists substrings of binary names,
application names or window classes that never start a meeting. It is a
substring match, so `["obs"]` also ignores `obsidian`: prefer specific names such
as `["obs-studio"]`.

The module turns each option into a `MEETING_NOTES_*` variable on the service
(`diarization.*` becomes `MEETING_NOTES_DIARIZATION`,
`MEETING_NOTES_DIARIZATION_THREADS` and `MEETING_NOTES_DIARIZATION_MAX_DELAY`).
The VAD models, the speaker model, whisper, ffmpeg and the claude path (from the
per-user profile) come from the Nix store, not from options.

## State files

Everything lives in `~/.local/share/meeting-notes`:

| Path | Content |
|------|---------|
| `state.json` | meetings and their status, written under a file lock |
| `control/` | `start.json` and `stop`, the manual start and stop requests |
| `work/<id>/` | `meta.json`, `transcript.txt`, `screen.txt`, `screens/`, `speakers.json`, `speakers.npz`, `fetched.ok` |
| `voices/` | voice prints, see [Diarization and voice prints](#diarization-and-voice-prints) |
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
of the native backend, the screenshots, the WAV files, the window embeddings
(`speakers.npz`) and the cache entries. `work/<id>/` text files, `speakers.json`,
`state.json`, the voice prints and the notes stay.

`~/Meetings` is never cleaned. Audio is not deleted if the audio directory sits
inside it. The screenpipe backend's audio in `~/.screenpipe/data` is left to
screenpipe.

## Slack

`slack.enable` makes `meeting-notes finish` post the result of each meeting.
It is off by default. The Slack API calls are covered by tests with a fake
`curl` only and have not been run against a real workspace: run
`meeting-notes slack-check` first, then test with `postTo = "dm"`.

### What gets posted

- Notes stage: a header message `*<title>*`, followed by ` · <N> min` when the
  meeting has a start and an end, then the notes file uploaded into that
  message's thread, titled `<title> – Notes`. The file keeps the name of the
  notes `.md` file.
- Transcript stage: the transcript file uploaded into the same thread, titled
  `<title> – Transcript`. State written before this change has no thread. Then
  the transcript gets its own header message and the upload goes into that
  one, and the meeting ends as `dm_only`.
- `slack_ts` and `slack_channel` stay in `state.json` as before, with
  `slack_files` listing the uploaded kinds (`notes`, `transcript`).
- The header title is escaped for Slack mrkdwn (`&`, `<` and `>` become
  `&amp;`, `&lt;` and `&gt;`), so a title cannot carry `<!channel>`, `<!here>`
  or a user mention.

A header that was posted when the upload then failed is saved at once under
`slack_threads` in `state.json`, with the files already uploaded. A retry of
the same stage reuses that header and uploads only the missing files, so it
never posts a second header. The entry is removed when the stage finishes or
the meeting is skipped. A stored thread is only reused for a sensitive meeting
when its channel is a direct message (an id starting with `D` that is not
`slack.channelId`).

The Slack calls are made by `finish`, never by Claude. With `slack.enable` the
prompt says `finish` does all the posting and Claude must not post, send or
share anything. Both prompts forbid reading `.env`.

### Destination

`slack.postTo` is `dm` (default) or `channel`.

- `dm`: header and files go to the direct message with `slack.userId`.
- `channel`: header and files go to `slack.channelId`. The bot must be a
  member of the channel, which `slack-check` arranges with
  `conversations.join` for public channels.
- Sensitive meetings: see the rule under `--sensitive` above. In short, never
  in the channel, never at all with `dm`, direct message only with `channel`.

The options become `MEETING_NOTES_SLACK_POST_TO`, `MEETING_NOTES_SLACK_CHANNEL`
and `MEETING_NOTES_SLACK_USER`. Without `MEETING_NOTES_SLACK_USER` the code
falls back to `SLACK_USER_ID` in `.env`, which older setups use.

### Slack app

Create the app from this manifest in the workspace admin, install it and copy
the bot token (`xoxb-...`).

```yaml
display_information:
  name: meeting-notes
features:
  bot_user:
    display_name: meeting-notes
    always_online: false
oauth_config:
  scopes:
    bot:
      - chat:write
      - files:write
      - im:write
      - channels:join
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

| Scope | Used for |
|-------|----------|
| `chat:write` | the header message |
| `files:write` | `files.getUploadURLExternal` and `files.completeUploadExternal` |
| `im:write` | `conversations.open` for the direct message |
| `channels:join` | `conversations.join` on a public channel |

A private channel needs an invitation of the bot instead of `channels:join`.

### Token

The token is the only secret. On Linux it is a sops secret: `secrets/meeting-notes.yaml`
holds `slack-bot-token`, encrypted for the age key in `.sops.yaml`. When that file
exists and `slack.enable` is on, sops-nix decrypts it to
`~/.config/meeting-notes/slack-bot-token` and the service gets
`MEETING_NOTES_SLACK_TOKEN_FILE` pointing at it. Without the file, the token is
read from `~/.local/share/meeting-notes/.env`, which the owner writes by hand:

```
SLACK_BOT_TOKEN=xoxb-...
```

A readable, non-empty token file wins over `.env`. To create or rotate the
secret, the owner runs `sops secrets/meeting-notes.yaml` from the repo, or pipes
the value into `sops encrypt --filename-override secrets/meeting-notes.yaml`.

It never goes in Nix options, in plain text in the repo, or in an argument. Every
authenticated call hands it to `curl --config -` on standard input. The file
bytes go to the pre-signed `upload_url`, which needs no token. Nothing prints
the token, and errors only quote the Slack error string. Claude is told never
to read `.env`.

### Rollout

1. Write `.env` with the token.
2. Run `meeting-notes slack-check`. It calls `auth.test`, then
   `conversations.join` on the channel when `postTo` is `channel`, then
   `conversations.open` on the user. It prints the team and bot names and ids,
   the channel and the direct message id, never the token. It exits 1 and
   prints `slack-check failed: <method> failed: <slack error>` on stderr when
   a step fails.
3. Set `slack.enable = true` with `postTo = "dm"`, rebuild, and watch a real
   meeting arrive in the direct message.
4. Switch `postTo` to `channel` once the direct message output is right.

`meeting-notes check` also shows `slack: on|off, post to dm|channel`.

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
