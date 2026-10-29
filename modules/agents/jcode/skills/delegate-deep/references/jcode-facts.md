# jcode mechanics behind delegate-deep

Verified against jcode rev `29d17a9` (Oct 2026) by reading source and by live
probes. Paths are relative to `crates/`. Re-verify when jcode is bumped: the
comm layer is mid-migration (`docs/SWARM_TASK_GRAPH.md` section 8a).

## Messaging

| Send | Reaches | Default delivery |
|---|---|---|
| `dm` | one session (id or unique friendly name) | `wake` |
| `broadcast` | sender's spawned subtree only; coordinator reaches the whole swarm | `notify` |
| `channel` | subscribers except sender; zero subscribers falls back to subtree | `notify` |

- `notify` never reaches a model. It is a `ServerEvent::Notification` to
  attached clients only (`jcode-app-core/src/server/client_comm_message.rs:422`).
  Headless workers have no client, so nobody sees it. Live probe confirmed.
- `interrupt` queues a soft interrupt, injected after the next tool result
  (points C/D in `agent/turn_streaming_mpsc.rs`). It never starts a turn.
- `wake` starts a turn on an idle attached agent (`server/live_turn.rs:210`),
  otherwise falls back to interrupt. Live probe: a `ready` worker woke and the
  queued interrupt rode along after it.
- Worker completion reports are display-only notifications
  (`server/swarm.rs:1672-1725`). They never wake the coordinator.
- A worker with no children that broadcasts reaches nobody.
- Channel posts cannot be read back later. Channels and shared context are
  slated for removal.

## Task graph (deep mode)

- Seed with `swarm task_graph mode=deep nodes=[{id, content, kind,
  depends_on, priority}]`. Unknown `kind` silently becomes `explore`
  (`jcode-plan/src/bridge.rs:30`). Use `implement` or `fix` for code.
  `priority` is a `u8`: a word like `"high"` is rejected with
  `invalid type: string "high", expected u8` (live run).
- Deep seed auto-inserts a root gate over every root node
  (`jcode-plan/src/dag/ops.rs:60-69`). It is `verify` when all roots are
  `implement`/`fix`, otherwise `critique`. Re-seeding after completion
  reopens it.
- `expand_node` turns a running node into a composite: children plus an
  auto gate `{node}::gate`. The parent re-runs as a synthesis step.
- `complete_node` in deep mode rejects empty `findings`, empty
  `what_i_did_not_check`, or unparseable `confidence`
  (`dag/ops.rs:703-747`).
- Gate passes must name every audited node id in findings or
  `open_questions` (up to 20 nodes, beyond that every non-high node), and
  cannot pass over an unaddressed `low` sibling (`dag/ops.rs:789-877`).
- A deep turn that ends without `complete_node` or `expand_node` re-queues the
  node to a fresh worker (`server/comm_control.rs:278-300`). The "fail on
  second offense" counter lives in `task_progress`, which every new
  assignment resets (`server/comm_control.rs:1622-1633`). Under `run_plan`
  re-queues are effectively unbounded until the driver's 200-loop cap.
- Every dispatched node gets an appended deep contract system reminder
  (`jcode-swarm-core/src/lib.rs:378-421`) and a conflicting "call report"
  reminder (`server/comm_control.rs:774`). The charter resolves this. Node
  content containing "do not expand this node" gets a bounded contract
  without `expand_node` (`jcode-swarm-core/src/lib.rs:383-397`).
- Auto gates (`{node}::gate`, `plan::gate`) get engine-written content only
  (`dag/ops.rs` `gate_content`, `root_gate_content`). Children from
  `expand_node` and `inject_gap` carry whatever text their creator wrote.
  Only `run_plan message=` reaches all of them.
- Dataflow: a node's prompt is hydrated with artifacts of its direct
  dependencies only (`jcode-plan/src/bridge.rs:227`).

## run_plan

- Background by default. Wakes the coordinator once, at terminal state.
  A second driver for the same session is refused.
- Fresh worker per node (`prefer_spawn=true`). Synthesis does not get the
  planner's context, so artifacts must be self-sufficient.
- `model` and `effort` apply to every worker of the run. Precedence: explicit
  param, then `agents.swarm_model` / `agents.swarm_effort`, then coordinator.
- `message` is appended to every assignment as "Additional coordinator
  instructions" (`jcode-plan/src/lib.rs:338`), gates included.
- `working_dir` is passed to every spawned worker
  (`server/comm_control.rs:1921`). Without it, workers inherit the
  coordinator's dir. File tools resolve relative paths against it
  (`jcode-tool-core/src/lib.rs:141-149`), and bash does not keep `cd`
  between calls.
- `timeout_minutes` (default 60) bounds each internal wait for a member
  status change. Exceeding it is a driver error, not a terminal state. It is
  not in the tool's JSON schema, but `run_plan` reads it
  (`tool/communicate.rs:1251`).
- A running driver picks up nodes that become ready during its wait, which
  includes newly seeded ones (`await_should_wake_for_new_ready`,
  `tool/communicate.rs:415`).
- Concurrency: `agents.swarm_max_concurrent_agents`, default 32 live.
- Every worker reports back to the session that ran `run_plan`, including
  children created by `expand_node`. The coordinator is the only relay.
- Workers spawn in `run_plan working_dir`, else the coordinator's dir.
- Terminal summary has counts and failed ids, no artifacts. `Ok` does not
  mean success: dependents of a failed node end as `blocked`.
- `retain_agents=false` (default) stops workers at the end. Driver errors
  (credential wave, 60 min await timeout, stall, 200 loops) keep workers.
- Server reload kills the driver, not the workers. Rerun `run_plan` to resume.
- Recovery: `swarm retry` re-dispatches to the old assignee, which no longer
  exists after `run_plan` cleanup (`server/comm_control.rs:513`). Use
  `swarm assign_task task_id=<id> prefer_spawn=true` instead: it spawns a
  worker and accepts a failed item whose dependencies are done
  (`tool/communicate.rs:3101`, `jcode-plan/src/lib.rs:731`). The `message`
  is appended as "Additional coordinator instructions".
- Coordinator can `complete_node` or `expand_node` an unowned ready node
  itself (`server/comm_graph.rs:138`).
- Spawn gating: explicit `spawn` and `assign_task prefer_spawn=true` go
  through `handle_comm_spawn`, which refuses a non-root requester unless the
  root session's effort is `swarm-deep` (`server/comm_session.rs:1390-1407`).
  `run_plan` spawns through `assign_next` -> `spawn_swarm_agent`, which has
  no such gate. A non-root session may drive a deep plan it seeded as a plan
  participant (`server/comm_control.rs:2603-2616`).

## Persistence and observation

- Plan, statuses and artifacts persist in
  `~/.jcode/state/swarm/<swarm_id sanitized>.json`, key
  `plan.node_meta.<id>.artifact_json`. The swarm id is `JCODE_SWARM_ID` when
  set, else `session:<root session id>` (`server/util.rs:405-419`).
  `dd.py init` records it in the run dir; `dd.py nodes` and `artifact` read it.
- `blocked` is never stored: it is computed from dependencies
  (`dag/mod.rs:104`). `dd.py nodes` computes it for failed ancestors.
- `plan_status` shows ids per state, failed reasons, low-confidence ids and a
  growth line, but no artifacts.
- Staleness: a running node with no heartbeat for 45 s becomes
  `running_stale`. Heartbeats run for the whole worker turn, so a worker
  polling inside its turn stays healthy.
- Stall watchdog: 600 s silent with no tool running flags the worker to the
  coordinator once. A long `bash` call counts as a running tool. The optional
  nudge (`agents.swarm_stall_nudge`) tells workers to `swarm report`, which
  the charter overrides.
- DM `wake` starts a turn on an idle target whose member still has an open
  event channel (`server/live_turn.rs:76-87`). Headless spawned sessions keep
  one: an idle headless probe woke on a `wake` DM. A TUI session whose client
  was closed has none and only sees DMs at its next turn.
- `swarm cleanup` after a clean `run_plan` finds nothing: `run_plan` already
  stopped its workers, and stopped members disappear from the persisted
  state.

## File activity alerts

- `edit`, `write`, `apply_patch`, `replace` record file touches. When a worker
  modifies a file a swarm peer modified earlier (30 min window), both get a
  soft interrupt "File activity: ..." naming the peer and its intent
  (`server.rs:2133-2288`).
- Detection only, after the fact. Bash edits, reads and paths in different
  worktrees are invisible to it.

## bash

- The bash safety gate refuses commands whose write target is computed at
  runtime (`> "$D/x"`, command substitution in a path) as irreversible.
  Write literal paths (live run).
- Foreground default timeout 120 s, max 600 s. Past it the command is
  promoted to a background task, not killed. Waits must stay under the
  explicit timeout to remain in-turn.
- `JCODE_SESSION_ID` is exported to every bash call. `dd.py` uses it as the
  lock holder id.
