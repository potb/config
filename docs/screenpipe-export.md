# screenpipe export

`modules/agents/screenpipe-export.nix` runs `export.py` every hour and writes
screenpipe's OCR text, audio transcriptions and hourly activity summaries into
Honcho. The same run also exports the meetings recorded by
[meeting-notes](meeting-notes.md). The script lives in
`modules/agents/screenpipe-export/`.

Screenpipe audio is disabled on charon, so the `speech` layer goes quiet and
meetings are the speech source. The audio code stays for hosts that still
record it.

## What it reads

From the local screenpipe API on `127.0.0.1:3030`:

- `/search` with `content_type=ocr`. Frames are grouped per window per five
  minutes and deduplicated, so one message covers a stretch of screen rather
  than every capture.
- `/search` with `content_type=audio`. Input devices are attributed to `peio`,
  output devices to `colleague`.
- `/activity-summary`, one message per hour, listing apps and windows with
  their minutes. Frames often arrive without `app_name` and `window_name`, so
  this is the only place the window names come from.

## The cursor

The hour in progress is never exported. `~/.local/state/screenpipe-export/cursor`
holds the last completed hour that was written, and each run exports from it to
the top of the current hour, then moves it forward. Hours are exclusive at the
start, so a message belongs to exactly one run and an hourly timer cannot
overwrite its own work.

`EXPORT_HOURS` is only the lookback of the first run, when no cursor exists yet.
A missed timer is caught up on the next run. `EXPORT_MAX_HOURS` (24 by default)
caps the catch-up so a machine that slept for a week does not export a week.

The cursor only advances when every message batch was accepted. A run that
fails halfway therefore repeats its hours on the next attempt, which is why the
script also skips content the session already holds: it reads the target
session and drops any message whose peer and whitespace-normalised content are
already stored.

## Layers

One Honcho session per UTC hour, named `screen-YYYY-MM-DD-HH`. Each message
carries a `layer` in its metadata: `screen-ocr`, `speech` or
`screen-activity`. Dropping the whole capture layer means deleting the sessions
whose id starts with `screen-`; dropping speech alone means deleting the
messages tagged `speech`. Meetings live in separate `meeting-` sessions with
their own layers, see Meetings.

Honcho does not keep session metadata. A session created with
`{"metadata": {"layer": "screenpipe"}}` reads back as `metadata: null` from
`GET /sessions/{id}` and from the session list, so the layer lives on the
messages and in the session name instead.

## Meetings

The meeting step reads `~/.local/share/meeting-notes/state.json` (`meetings`
and `processed`) and the files the meeting-notes pipe wrote. It does not touch
the screenpipe cursor: screen layers and meetings succeed or fail
independently, and a failure in one never blocks the other. The run exits
non-zero if either failed.

A meeting is exported when all of these hold:

- Its processed status is terminal and not a skip: `done`, `posted`,
  `dm_only` or `failed` (`skipped` and `skipped_short` never export, nor does
  a meeting carrying a `skip_reason`). A meeting still waiting for its
  transcript (`notes_saved`, `notes_posted`) waits for a later run.
- It has an end time and a `dir` holding `notes.md` or `transcript.md`. A
  relative `dir` is resolved against the directory of `state.json`.
- It is not sensitive: `sensitive` set on the processed entry or on the
  meeting record. Sensitive meetings are never exported, whatever their
  status. Flagging a meeting sensitive after it was exported does not remove
  it, see below.

Each meeting is one Honcho session, `meeting-<meeting id>` (for example
`meeting-20261118-100141`). Every message carries `layer`, `meeting_id`,
`title`, `app`, `start` and `end` in its metadata.

| Layer | Peer | Content |
| --- | --- | --- |
| `meeting-notes` | `meeting-notes` | `notes.md`, one message, or sections packed up to 4000 characters when longer. Created at the end of the meeting. |
| `meeting-transcript` | `peio`, a speaker slug, or `colleague` | One message per speaker turn, content `[hh:mm] Name: text`. Metadata adds `speaker` and `time`. |

The transcript is the corrected one: `**[hh:mm] Name :** text` paragraphs, a
`#` title and a `_..._` participants line at the top, a `_Corrections..._`
footer. The times are local to the machine (the same zone meeting-notes uses
to write them) and are converted to UTC for `created_at`; a turn that jumps
back by more than twelve hours counts as the next day. Consecutive turns by
the same speaker in the same minute are merged into one message, because the
corrected transcript shares the block timestamp between turns.

Speaker attribution:

- `Peïo` is the owner and goes to `peio`, the peer that audio input already
  uses.
- A label with `?` (`Quentin (?)`, `Participant 1 (Bastien ?)`) or starting
  with `Participant`, `Speaker`, `Unknown` or `Inconnu` goes to `colleague`.
  This includes `Peïo (?)`: an uncertain attribution never lands on the owner.
- Any other name becomes a lowercase ASCII slug peer, `vincent`. A first name
  that matches exactly one entry of the participants line expands to it:
  `Hugo` with `Hugo Danaguezian (Mazmez)` listed is `hugo-danaguezian`.
  Different meetings can list the same person differently, so a person may
  appear under a first-name slug in one meeting and a full-name slug in
  another.

Peers are created with `POST /peers` before the first message, like the screen
peers. A message over 4000 characters is split on paragraph boundaries, then
at a line break or space, and the parts carry `part` as `1/3`.

### Idempotence

`~/.local/state/screenpipe-export/meetings.json` records exported meeting ids
(`exported`) and the progress of a meeting that failed halfway (`partial`). It
is written atomically with a temporary file and `os.replace`, after each batch
and when a meeting finishes. A meeting is added to `exported` only when every
batch was accepted, so a failed run retries on the next hour. Meetings go out
in batches of 20 messages, so a timeout after Honcho stored a batch it never
acknowledged can duplicate at most those 20. A meeting that fails, from a
network error or an unreadable file, is logged and skipped; the meetings after
it are still exported.

Honcho's `messages/list` only ever returns the first 50 messages of a session
(see Quirks), so the content check alone cannot protect a meeting of a
hundred messages. `partial` keeps how many messages were already sent; a retry
skips them, then still runs the content check on the rest. If the message
count changed between attempts the progress is ignored and only the content
check applies. Losing `meetings.json` re-reads the sessions and re-sends
whatever the first 50 messages do not cover, so avoid deleting it.

A meeting is exported once. Editing `notes.md` or the transcript afterwards,
or re-running the pipe for it, does not re-export. To redo one, delete its
session in Honcho and remove its id from `exported`.

### Deleting meetings

Delete the session `meeting-<id>` in Honcho to drop one meeting, or every
session whose id starts with `meeting-` for the whole layer. Delete the
messages tagged `meeting-transcript` to drop the speech only. Then remove the
ids from `meetings.json`, or the meeting stays marked as exported.

### Options

`MEETING_NOTES_STATE` is the path of `state.json` (default
`~/.local/share/meeting-notes/state.json`). `EXPORT_MEETINGS=0` turns the step
off (default `1`). `EXPORT_MEETINGS_STATE` moves `meetings.json`. A missing
`state.json` skips meetings silently. The module sets them from
`services.screenpipe-export.meetings` and `meetingNotesState` (relative to the
home directory).

### Dry run

`EXPORT_DRY_RUN=1` or `--dry-run` prints what would be exported for the
meetings that are eligible and not yet exported: session id, message count and
size, then a line per peer and layer. It makes no network call and writes no
state. It also skips the screen export entirely, so no screenpipe or Honcho
access is needed and neither key is read.

```
python3 modules/agents/screenpipe-export/export.py --dry-run
```

### Tests

```
cd modules/agents/screenpipe-export
python3 -m unittest test_export
```

## Credentials

The screenpipe API key comes from `screenpipe auth token` at run time. The
Honcho key is a sops secret: `secrets/honcho.yaml` holds `honcho-api-key`,
decrypted by `sops-nix` to `~/.config/honcho/api-key` with mode 0400, and the
module passes that path to the script as `HONCHO_API_KEY_FILE`. Rotating the
key means editing `secrets/honcho.yaml` with `sops secrets/honcho.yaml`.

## What it drops

- Windows or pages matching the skip pattern: password managers, banks,
  tax and social security portals, Stripe's dashboard, anything matching
  `password`, `secret`, `2fa`.
- OCR text shorter than 60 characters and audio shorter than 15 characters.
- Screenpipe's own PII filter is not requested: it returns 503 when its
  remote filter is unreachable. Redaction of IP addresses and keys happens at
  index time instead.

## Running it

```
systemctl --user start screenpipe-export
journalctl --user -u screenpipe-export -n 50
```

A run is a oneshot: it exits when the export is written, and prints
`exported N new messages of M collected`. `nothing to export` means the cursor
is already at the current hour. The timer fires hourly with up to five minutes
of jitter.

To rebuild a day after deleting it, remove the cursor and pass a lookback:

```
EXPORT_HOURS=24 HONCHO_WORKSPACE=... HONCHO_API_KEY_FILE=... python3 export.py
```

## Quirks worked around

- `messages/list` caps a page at 50 rows and ignores the page number past the
  first page: page two repeats page one. `total` is the real count, so the
  duplicate check stops as soon as a page brings no new message ids.
- Re-reading the same hour does not return identical OCR: screenpipe's offset
  pagination over a live index shifts, so a replayed hour produces a few
  slightly different messages. The cursor, not the duplicate check, is what
  keeps normal runs clean.

## Volume

OCR is roughly 40 messages per six hours of active use, audio one per spoken
chunk, activity one per active hour. An hour of work lands tens of messages,
not hundreds, which keeps derivation cheap.
