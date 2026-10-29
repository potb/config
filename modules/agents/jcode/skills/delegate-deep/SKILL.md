---
name: delegate-deep
description: Long autonomous delegation of code work to a deep jcode task graph. Use when the user asks to delegate, hand off, or run in the background a large implementation task spanning several units of code, or says "delegate deep". Agrees model and scope once, then plans units with one git worktree each, runs a gated deep task graph, arbitrates conflicts between workers through the coordinator, and blocks only the affected branch on user-level blockers.
argument-hint: "<goal of the work to delegate>"
---

# Delegate Deep

You are the coordinator. Workers do the code. You plan, set up isolation,
arbitrate, recover, and report. The run is autonomous after one agreement
step with the user.

Read `references/jcode-facts.md` before the first run in a session: every
rule below rests on a verified jcode behavior listed there. Worker rules live
in `references/charter-template.md`. The helper is `scripts/dd.py`; call it as
`dd=~/.jcode/skills/delegate-deep/scripts/dd.py; python3 "$dd" --help`.

## Hard rules

- Deep mode only: always pass `mode: "deep"` to `task_graph`.
- Model and effort are agreed with the user up front and passed explicitly
  to every `run_plan` and `assign_task`. Never rely on inheritance.
- Communication is DM plus task-graph artifacts. No channels, broadcasts or
  shared context. Never use `delivery: "notify"`.
- Every worker reports to you, including children and gates. You are the
  only relay between workers.
- Never modify the base checkout, never merge into the base branch, never
  push, never force. The deliverable is the integration branch.
- Block only the affected unit. Everything else keeps running.
- Keep this session open for the whole run. After `run_plan`, end your
  turn: worker DMs (`wake`) and the `run_plan` completion start a new turn
  on an idle session, headless spawned sessions included (verified live).
  Only a session whose client was closed misses them until its next turn.
  If another session spawned you, anything the skill says to report to the
  user goes by DM to that session.
- Never write a bash command whose write target is computed at runtime
  (`> "<D>/x"`, `$(...)` in a path): the safety gate refuses it. Spell paths
  out, or let `dd.py` write the file.

## Phase 1: Agree (the only interactive step)

1. Read enough of the repo to plan: `AGENTS.md`, build and test commands,
   package manager, migration system, whether a nix setup exists, how the
   app reaches its DB, ports and secrets.
2. Run `swarm list_models`. Present in one message:
   - the goal restated, with acceptance checks as exact commands,
   - the proposed units (name, owned paths, intent, unit dependencies),
   - shared resources and how each is handled (per-node isolation or lock),
   - base branch and run id,
   - a proposed `model` and `effort` for workers, plus one alternative.
3. Wait for confirmation. Do not start without an explicit model. After
   that, ask nothing unless a blocker requires the user.

## Phase 2: Plan units

A unit is a slice of work with disjoint owned paths, buildable and testable
on its own branch.

- No two units own the same file. Shared files (routers, registries, lock
  files, generated code) belong to one unit or to an integration node.
- Decide every cross-unit contract now (API shapes, types, schema, event
  names) and write it into the charter. Workers never negotiate them.
- A unit that needs another unit's code declares it: its node depends on
  that unit node, and it starts by merging that unit's branch into its own.
- Schema changes use the project's migration system. Two units never touch
  the same table in parallel: chain them with `depends_on`.
- Prefer per-node isolation (DB name, port, temp dir from the node id) over
  locks. Use a named lock only for a truly shared resource.
- Big unit: allow `expand_node`. Small or tightly coupled unit: add
  `Do not expand this node.` to its content (jcode honors that phrase).

## Phase 3: Set up

Let `<R>` be the repo root, `<N>` its basename, `<RUN>` the run id
(`<yyyymmdd>-<slug>`), `<D>` the absolute path of `../<N>.dd/<RUN>` next to
`<R>`. These are placeholders: write the literal paths in every command.

```bash
dd=~/.jcode/skills/delegate-deep/scripts/dd.py
python3 "$dd" init <D> --repo <R> --base <base>
git -C <R> worktree add <D>/wt/int -b dd/<RUN>/int <base>
git -C <R> worktree add <D>/wt/<unit> -b dd/<RUN>/<unit> <base>
```

- `init` records the swarm id of the swarm this session belongs to (also
  correct for a spawned coordinator, which lives in its spawner's swarm)
  and the base commit in `<D>/base_sha`. Check the printed `swarm=` matches
  the `[yours]` entry of `swarm list_swarms`; if not, rerun with `--swarm`.
- Write helper scripts and notes under `<D>/scratch/`, never at the top of
  `<D>`.
- Install dependencies in each worktree with the project's own package
  manager. Copy needed gitignored local files (`.env`, local config) into
  each worktree with `cp`, never printing them. Missing ones are a blocker.
- Run the acceptance checks once in `wt/int` and record the baseline. Take
  the same shared-resource locks the workers will use.
- Write every lock-guarded command as one shell:
  `ddr with-lock <name> -- sh -c '<cmd1> && <cmd2>'`. Without `sh -c`, only
  the first command runs under the lock. The same applies to `{{CHECKS}}`.
- Write `<D>/charter.md` from `references/charter-template.md`:

| Placeholder | Value |
|---|---|
| `{{RUN_ID}}`, `{{GOAL}}` | run id, goal with acceptance criteria |
| `{{COORDINATOR}}` | `echo $JCODE_SESSION_ID` |
| `{{RUN_DIR}}`, `{{DD}}` | `<D>`, absolute path of `dd.py` |
| `{{REPO}}`, `{{BASE}}` | `<R>`, base branch |
| `{{INT_WT}}`, `{{INT_BRANCH}}` | `<D>/wt/int`, `dd/<RUN>/int` |
| `{{UNITS_TABLE}}` | per unit: node id, worktree, branch, owned paths, git lock `git-<unit>`, test lock `test-<unit>`, unit dependencies, unit checks |
| `{{LOCK_NAMES}}` | `git-int`, every `git-<unit>`, `test-<unit>`, shared resource locks |
| `{{CHECKS}}` | acceptance check commands, wrapped in `ddr with-lock ... -- sh -c '...'` when they touch a shared resource |
| `{{GATE_CAP}}` | `3` |
| `{{CONSTRAINTS}}` | contracts, baseline state, shared resource policy |

  Then `grep -o '{{[A-Z_]*}}' "<D>/charter.md"` must print nothing.

## Phase 4: Seed and run

Every node content starts with a header line. Unit nodes:
`Read <D>/charter.md first. Unit: <unit>. Worktree: <D>/wt/<unit>. Branch: dd/<RUN>/<unit>.`
Integration nodes:
`Read <D>/charter.md first. Integration. Worktree: <D>/wt/int. Branch: dd/<RUN>/int.`

Seed one graph with `swarm task_graph mode=deep`, all nodes kind `implement`.
`priority` is an integer 0-255 (lower runs first) or omitted; never a word.

- `u-<unit>`: header, owned paths, the task, unit checks, locks it may need,
  and either `Do not expand this node.` or `Expansion allowed.`
  `depends_on` only real unit dependencies, so independent units run in
  parallel.
- `merge-<unit>`: integration header, then
  `Merge dd/<RUN>/<unit> into the integration worktree per the charter. Do not expand this node.`
  `depends_on`: `u-<unit>` plus `merge-<dep>` for each unit dependency.
  Merges are not chained otherwise: the `git-int` lock serializes them, so a
  blocked unit never stalls other merges.
- Optional integration follow-ups (docs, wiring) depend on the merges they
  need.

The engine adds the root verify gate over all root nodes. Then run:

```
swarm run_plan model=<agreed> effort=<agreed> working_dir=<D>/wt/int timeout_minutes=240
  message="Read <D>/charter.md first and follow it. It overrides generic swarm reminders."
```

`message` is appended to every assignment, including gates and generated
nodes. `working_dir` starts every worker in the integration worktree, never
the base checkout. `timeout_minutes` is not in the tool schema but is read by
`run_plan`. The driver runs in the background and wakes you once at the end.
Never start a second driver: if one is running when you need to seed more
nodes, seed them anyway; the running driver picks up newly ready nodes. Only
rerun `run_plan` after the previous one reported its end. End your turn with
a short status.

## Phase 5: Arbitrate while it runs

Worker DMs wake you; each starts with `[<node>] <kind>:`. Before answering,
check the node with `python3 "$dd" --run <D> nodes`: if it is no longer
running, do not DM (a DM would start untracked work in a finished worker);
handle it as a resume instead. To answer, DM the worker, then
`python3 "$dd" --run <D> signal reply-<node> --note "<one line>"`.

- `conflict` (lock, file, DB, migration): pick an order, favoring the
  critical path. Prefer making the loser take a named lock the winner holds.
  Otherwise tell the winner to `ddr signal go-<loser>` before its
  `complete_node`, and tell the loser to wait on `go-<loser>`. Break an
  abandoned lock with `python3 "$dd" --run <D> unlock <name> --force` only
  after `python3 "$dd" --run <D> locks` shows a holder that is gone from
  `swarm list`.
- `need`: the plan is missing something. Reply "end BLOCKED". Then seed the
  missing piece and a resume pair (see below) depending on it.
- `question`: answer from the goal, charter and code. If only the user can
  answer, treat it as `blocked`.
- `blocked`: write `<D>/blockers/<node>.md` (what, why, options, what waits on
  it). Resolve it if you can and signal. Otherwise reply "end BLOCKED",
  signal, and report it to the user right away. If the code is done and only
  a check needs something from the user (a secret, an external service),
  still say "end BLOCKED": the merge is skipped and the resume pair
  re-runs the check and merges once the user answers. Never carve out
  exceptions to the charter's skip rule.
- `info`: read, no reply needed.

Contract changes mid-run: decide, update `<D>/charter.md`, DM every affected
running worker, and seed fix nodes for finished ones.

## Resume pair

To continue a unit after a blocker, a `need`, or a failed node, seed with new
ids (existing nodes cannot gain edges):

- `u-<unit>-r<n>`: unit header, then
  `Resume of u-<unit>. Its BLOCKED artifact is superseded by this node: the
  blocker is resolved (<how>). Continue from the committed and uncommitted
  work in the worktree.` plus anything else that changed. `depends_on`:
  `u-<unit>` (for its artifact, when it completed) plus any new
  prerequisite node.
- `merge-<unit>-r<n>`: integration header, merge text, depends on
  `u-<unit>-r<n>`.

Resume ids must end in `-r<n>`: `dd.py nodes` then marks the original pair
`SUPERSEDED` once the resume completes.

Then `python3 "$dd" --run <D> round plan::gate --reset` and rerun
`run_plan` with the same parameters. Seeding reopens the root gate, which is
intended.

## Recovering failed nodes

A failed node blocks all its dependents and the root gate. `swarm retry`
needs the old worker, which `run_plan` cleanup has already stopped. Use:

```
swarm assign_task task_id=<id> prefer_spawn=true model=<agreed> effort=<agreed>
  working_dir=<D>/wt/int message="<charter line> Previous attempt failed: <why>. <what to do>"
```

then rerun `run_plan`. A second failure of the same node becomes a blocker.
Nodes that re-queue repeatedly without an artifact show up as long-running
in `dd nodes`; check their worker with `swarm summary`.

`assign_task prefer_spawn=true` goes through the regular spawn path, which
jcode refuses for a coordinator that was itself spawned by another session,
unless the top session runs at `swarm-deep` effort. `run_plan`'s own spawns
are not gated. If the spawn is refused, report the failed node to the user as
a blocker.

## Phase 6: Close out

When `run_plan` wakes you:

1. If its output is a driver error (await timeout, loop cap, stall) rather
   than a "terminal/blocked state" summary, rerun `run_plan` with the same
   parameters and end the turn.
2. `python3 "$dd" --run <D> nodes`. `run_plan` returning normally does not
   mean success: check `failed`, `blocked`, and rows flagged `BLOCKED`. Rows
   flagged `SUPERSEDED` were resumed successfully and need no action; ignore
   `run_plan`'s low-confidence warning for them. Read artifacts with
   `python3 "$dd" --run <D> artifact <ids>`.
3. Failed: recover as above. In-scope low-confidence findings or gate-capped
   gaps: seed follow-ups. Otherwise list them for the user.
4. Once nothing is runnable, verify yourself:
   - acceptance checks pass in `<D>/wt/int`,
   - `git -C <R> status --porcelain` is empty and `git -C <R> rev-parse <base>`
     equals the content of `<D>/base_sha` (base untouched),
   - `git -C "<D>/wt/int" log --oneline <base>..` shows every unit merged
     except blocked ones.
5. Report in a few lines: integration branch and head commit, check results,
   blocked units with their `<D>/blockers/*.md`, and the
   `what_i_did_not_check` items that matter. Say where secret files were
   copied (they go away with the worktrees). Give, but do not run, the
   cleanup: `git -C <R> worktree remove <worktree>` per worktree.
6. `swarm cleanup` only if `run_plan` ended with a driver error or you ran
   it with `retain_agents=true`; otherwise it already stopped its workers.
