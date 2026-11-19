# Workflow and shipping tracker: shared contract

Every piece below is written by a different builder. This file is the only
agreement between them. Change it only together with every consumer.

Home: `H = ~/.config/herdr-app`. Scripts live in `H/tools/` (not a mod folder,
so herdr does not load them). Data lives in `H/data/`. Scripts are Python 3
standard library only, run as `python3 -I <script>`, and write every output
file atomically (write `<file>.tmp`, then `os.replace`).

## Pieces

| Piece | Path | Role |
|---|---|---|
| ship scanner | `H/tools/scan-ship.py` | GitHub PRs and Linear dependencies |
| sidebar | `H/mods/agents-potb/` | agents list, grouped by remote repo |
| ship sidebar | `H/mods/ship-side/` | stuck PRs and blockers in the sidebar, the only shipping view; also runs the ship poller and sends its notifications |
| usage | `H/mods/claude-usage/` + `H/tools/scan-usage.py` | Claude plan usage in the sidebar, from the claude CLI `get_usage` control request |
| layout | `H/layouts/potb.json` | clone of main without the status bar: agents, ship and usage blocks in the sidebar |

The workflow tracker (`scan-wf.py`, `agent-detail.py`, `wf-board`, `wf-agent`) was deleted on 2026-11-17; the workflow sections below describe the data it read.

## Where Claude Code workflow data is

- Run dir: `~/.claude/projects/<slug>/<sessionId>/subagents/workflows/wf_<id>/`
  - `journal.jsonl`: events `launched` {}, `started` {key, agentId, label, phase},
    `result` {key, agentId, result, toolsUsed}, `failed` {key, agentId}. No
    timestamps. A retry reuses `key` with a new `agentId`: the last event per key
    decides that unit's state.
  - `agent-<agentId>.meta.json`: description (= label), workflowPhase, model
    (alias), pickedEffortModel.
  - `agent-<agentId>.jsonl`: transcript. Rows have `timestamp` (ISO UTC), `type`
    (user, assistant, attachment, api-request, ...). Assistant content blocks are
    separate rows repeating `message.id` and `message.usage`: dedupe by
    message.id when summing tokens. tool_use blocks: `message.content[].type ==
    "tool_use"` {id, name, input}. tool results: user rows with
    `message.content[].type == "tool_result"` {tool_use_id, is_error}. API errors:
    assistant rows with `isApiErrorMessage: true`, text in message.content[0].text.
    Final structured output: `type == "attachment"` and `attachment.type ==
    "structured_output"`, payload in `attachment.data`.
- Run summary, only after the run ends:
  `~/.claude/projects/<slug>/<sessionId>/workflows/wf_<id>.json` with status
  (completed, killed, failed), error, durationMs, startTime, totalTokens, logs[],
  phases[{title}], workflowName, scriptPath, workflowProgress[]. It can exceed
  1 MiB (it embeds the script): read it from Python, never from a mod.
- Live run phases and script: the parent session transcript
  `~/.claude/projects/<slug>/<sessionId>.jsonl` contains a tool result with
  `Run ID: wf_<id>` and `Script file: <path>`; the script's
  `export const meta = {... phases: [{title}]}` gives phase order.
- Owning session and terminal: `~/.claude/sessions/<pid>.json` {pid, sessionId,
  cwd, name}; the process is alive when `/proc/<pid>` exists; its herdr terminal
  is `HC_TERMINAL_ID` in `/proc/<pid>/environ`. Never read `~/.claude/sessions/*.key`.

## Output 1: `scan-wf.py`

Run: `python3 -I H/tools/scan-wf.py`. Scope: runs whose journal changed within
48 h, plus every run of a live session. Must finish in under 5 s on a warm cache
(cache in `H/data/wf-core/cache.json`, keyed by path + size + mtime; finished
agents are never re-read). Reads at most the last 64 KiB of an unfinished
agent's transcript.

stdout, one JSON object (small, goes to setShared after removing `events`):

```json
{ "ok": true, "ts": 1794768790337, "runsLive": 2, "agentsRunning": 47,
  "stuck": 3, "failed": 1,
  "sessions": { "t8": { "terminal": "t8", "sessionId": "2d917eaa-...", "name": "staging",
                        "runs": 3, "live": 1, "line": "Build 412/600", "stuck": 2, "failed": 1 } },
  "events": [ { "kind": "stuck", "terminal": "t8", "runId": "wf_7a33eedf-331",
                "title": "t8 / effect-campaign : 5 stuck",
                "body": "3 api-error (Fable limit), 2 hung-tool (Bash)" } ] }
```

`sessions` is keyed by herdr terminal id, else by `sessionId` when the session
has no terminal. `line` is the live run's current phase as `<phase> <done>/<started>`,
or "" when nothing is live. `events` holds only transitions since the previous
scan (an agent entering stuck or failed), grouped one per run; the scanner keeps
what it already reported in `H/data/wf-core/notified.json`. On any error: `{"ok":
false, "error": "..."}`, exit 0.

`H/data/wf-core/state.json`:

```json
{ "ts": 0,
  "sessions": [ { "sessionId": "", "pid": 0, "alive": true, "terminal": "t8",
                  "cwd": "", "name": "", "project": "<slug>" } ],
  "runs": [ { "runId": "wf_...", "sessionId": "", "terminal": "t8", "dir": "",
              "status": "running|completed|killed|failed|orphan", "name": "",
              "scriptPath": "", "startedAt": 0, "lastActivityAt": 0, "endedAt": 0,
              "durationMs": 0, "error": null, "logs": ["last 20"],
              "phases": [ { "title": "Build", "done": 0, "running": 0, "failed": 0, "stuck": 0 } ],
              "counts": { "started": 0, "done": 0, "running": 0, "failed": 0, "stuck": 0, "retries": 0 },
              "tokens": { "input": 0, "output": 0, "cacheRead": 0, "cacheCreate": 0 },
              "agentsFile": "H/data/wf-core/runs/wf_....json" } ] }
```

Times are epoch ms. `runs` sorted: live first, then by lastActivityAt desc.
`state.json` must stay under 1 MiB (mods read it with readTextFile).

`H/data/wf-core/runs/<runId>.json` (one per run in scope; may be large, the
board reads it through exec + python/jq filtering, see board section):

```json
{ "runId": "wf_...", "agents": [ { "agentId": "", "key": "", "label": "implement:TECH-1698:r2",
   "phase": "Build", "model": "sonnet", "effortModel": "claude-opus-5-5",
   "state": "running|done|failed|stuck", "reason": null, "reasonDetail": "",
   "attempts": 1, "startedAt": 0, "lastAt": 0, "lastTool": "Bash",
   "lastToolSummary": "", "tokens": { "input": 0, "output": 0, "cacheRead": 0, "cacheCreate": 0 },
   "transcript": "/abs/agent-<id>.jsonl", "ticket": "TECH-1698" } ] }
```

One entry per key (retries folded, `attempts` counts them; the entry describes
the latest attempt).

Stuck reasons, first match wins, thresholds read from `H/data/wf-core/config.json`
(created with these defaults when missing):
1. `api-error`: the last assistant row has isApiErrorMessage. Detail: the text.
2. `hung-tool`: a tool_use without tool_result older than its `input.timeout`/1000
   + 60 s (Bash default 120 s; other tools 600 s). Detail: tool name and command.
3. `loop`: 4 or more identical tool inputs in the tail, or 3 consecutive is_error results.
4. `waiting-on-human`: a pending AskUserQuestion.
5. `idle`: no pending tool and more than 300 s since the last row.
6. `orphan`: run without summary file whose session process is gone; every
   unfinished agent of it is stuck with this reason, and the run status is `orphan`.
`hung-child` is optional: a child process of the session pid older than the
pending tool's timeout.

## Output 2: `agent-detail.py`

Run: `python3 -I H/tools/agent-detail.py <transcript> [--turns 8]`. stdout:

```json
{ "agentId": "", "label": "", "phase": "", "model": "", "effortModel": "",
  "turns": [ { "ts": 0, "role": "assistant|user", "kind": "text|tool_use|tool_result",
               "text": "<= 300 chars", "isError": false } ],
  "pending": { "name": "Bash", "summary": "", "ageS": 0, "timeoutS": 0 },
  "final": null, "error": null,
  "tokens": { "input": 0, "output": 0, "cacheRead": 0, "cacheCreate": 0 } }
```

`final` is the structured_output data (or the journal result) when done.

## Output 3: `scan-ship.py`

Run: `python3 -I H/tools/scan-ship.py [--linear]`. Without `--linear` it only
refreshes PRs and reuses the last Linear data. The mod calls it every 90 s and
adds `--linear` every 180 s. GitHub through `gh api graphql` (repo
BeCosto/beakon). Linear through `https://api.linear.app/graphql`, header
`Authorization: <key>` (no Bearer), key read from `H/data/linear/key`, never
printed, logged or copied into any output. Config `H/data/linear/config.json`
(created when missing): `{ "projects": ["Effect adoption"], "satisfied": ["Done",
"Canceled", "Duplicate", "On Staging"], "staleHours": 12, "team": "TECH" }`;
projects may be names or slug ids, the scanner resolves them. Read-only: never
write to GitHub or Linear.

stdout:

```json
{ "ok": true, "ts": 0,
  "prs": { "open": 9, "stuck": 7, "conflict": 3, "red": 1, "cancelledRequired": 1,
           "pendingLong": 0, "readyUnmerged": 0, "draftForgotten": 3, "stackWaiting": 0 },
  "tech": { "startable": 4, "rootBlockers": 2, "noPr": 2, "stale": 1, "awaitingMain": 30 },
  "events": [ { "kind": "pr|tech", "title": "", "body": "", "url": "" } ],
  "errors": [] }
```

`H/data/ship-core/prs.json`:

```json
{ "ts": 0, "prs": [ { "number": 0, "title": "", "url": "", "isDraft": false,
  "base": "staging", "head": "", "ticket": "TECH-1", "ageH": 0, "idleH": 0,
  "mergeState": "", "mergeable": "", "autoMerge": false,
  "required": { "pass": 0, "fail": 0, "pending": 0, "cancelled": 0 },
  "reason": null, "reasonDetail": "", "failedRunIds": [], "worktree": null,
  "ticketTitle": "", "ticketUrl": "",
  "owner": { "terminal": "t8", "runId": "wf_..." } } ] }
```

`prs.json` keeps an open PR when the viewer authored it or when its ticket is one
of the viewer's Linear tickets: every issue assigned to the viewer whose state
type is neither completed nor canceled, across all projects, paged. That set is
cached in `H/data/ship-core/my-tickets.json` and reused when Linear cannot be
read. `ticketTitle` and `ticketUrl` come from it, null for a PR outside it.
The sidebar lists stuck PRs under « Needs you » and every other kept PR under
« In flight ».

PR reasons (first match): `conflict` (DIRTY or CONFLICTING), `red` (a required
check failed), `cancelled-required` (BLOCKED with a cancelled required check and
no newer run on the head), `pending-long` (required check pending over 20 min),
`stack-waiting` (base is another open PR's head), `ready-unmerged` (not draft,
CLEAN, idle over 1 h), `draft-forgotten` (draft, idle over 24 h). Required checks
come from the repo rulesets (`gh api repos/BeCosto/beakon/rulesets`), cached a
day. `worktree`: the local path from `git -C ~/projects/costo/beakon worktree list
--porcelain` whose branch is `head`. `owner`: the wf-core agent whose label or
ticket matches the PR ticket, from `H/data/wf-core/runs/*.json`.

`H/data/ship-core/linear.json`:

```json
{ "ts": 0, "projects": [ { "name": "", "url": "", "counts": { "Implementing": 6 },
   "startable": [ISSUE], "rootBlockers": [ { "issue": ISSUE, "blocksTransitively": 0 } ],
   "noPr": [ISSUE], "stale": [ISSUE], "awaitingMain": [ISSUE] } ] }
```

ISSUE = `{ "identifier": "TECH-1", "title": "", "url": "", "state": "", "updatedAt": 0,
"staleH": 0, "blockers": ["TECH-2"], "pr": 0, "owner": { "terminal": "", "runId": "" } }`.
An issue's blockers are its `inverseRelations` of type `blocks`; a blocker is
satisfied when its state name is in `satisfied`. Startable: Todo or Backlog with
every blocker satisfied. Root blocker: an unsatisfied blocker that is itself
Implementing, In Review or Needs Human, ranked by how many issues it blocks
transitively (DFS with cycle guard). No PR: Implementing or In Review without a
github.com/BeCosto/beakon/pull attachment and no open PR whose head contains the
identifier. Stale: Implementing, In Review or Needs Human not updated for
`staleHours`. Awaiting main: On Staging.

## Shared state and toasts

- `setShared("wf.summary", <scan-wf stdout without events>)` and
  `setShared("ship.summary", <scan-ship stdout without events>)`, only when the
  value changed. Nothing else goes to shared state (it is persisted to
  shared.json and re-renders every mod).
- my-status is the only poller (it is always shown). It runs scan-wf every 10 s
  and scan-ship as above, never two runs of one script at once, and calls
  `notify` once per event: wf events with action `agent.focus {terminal}`, ship
  events opening the ship board.
- Opening views: board `run("tab.new", {name: "Workflows", mod: "wf-board",
  props: {terminal?}})`; ship board `run("tab.new", {name: "Shipping", mod:
  "ship-board", props: {section?: "prs"|"linear"}})`; agent window
  `openOverlay({mod: "wf-agent", kind: "window", key: "wf-agent", width: 760,
  height: 640, props: {transcript, agentId, runId, terminal}})`. Before tab.new,
  a view first looks for an existing tab with that name in `spaces()` and selects
  it instead of opening a second one.

## Rules for every builder

- Read `H/AGENTS.md`, `H/herdr.d.ts` and `H/gpui-kit.d.ts` before writing a mod;
  use shipped mods in `H/mods/` (agents, changes, peek, workspace-status, confirm)
  as templates. Never edit a shipped mod folder or a shipped layout.
- Use `theme()` colours, animate natively, no timers just to redraw except a
  15 s clock for elapsed labels.
- Every mod must pass `herdr-app check <mod folder>`; every script must run
  against the real data on this machine and its output must parse with `jq`.
- No `herdr-app do`, no `hc send/run/kill`, no git or gh writes, no Linear writes
  while building. User-facing text is English.
- Writes from the UI (ship board only): `gh run rerun <id> --failed --repo
  BeCosto/beakon` and `gh pr ready <n> --repo BeCosto/beakon`, each behind the
  shipped `confirm` dialog. No merge button.
