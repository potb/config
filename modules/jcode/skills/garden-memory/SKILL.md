---
name: garden-memory
description: Use when asked to garden, consolidate, prune, or clean up memories. Maintains the memory graph - merges duplicates, resolves contradictions, prunes dead memories, verifies stale facts, and extracts from missed sessions.
allowed-tools: memory, bash, read, write, batch, todo, session_search
---

# Garden Memory

Full graph-wide memory consolidation. This is the interactive version of the
ambient garden cycle defined in `crates/jcode-app-core/src/ambient/prompt.rs`.

## Priority order

Highest value first. Duplicates and contradictions before pruning. Verify stale
facts only if budget remains.

1. **Consolidate duplicates** - semantically similar memories merge into one
   authoritative entry.
2. **Resolve contradictions** - when two memories disagree, determine which is
   true, write the corrected version, delete the wrong one. Never leave both.
3. **Prune dead memories** - superseded entries, one-off session trivia,
   completed TODOs, weak memories (confidence < 0.05 AND strength <= 1).
4. **Verify stale facts** - check factual memories against the actual codebase
   or filesystem. Facts about file paths, config values, and test status rot fast.
5. **Extract from missed sessions** - use `session_search` for recent work not
   yet reflected in memory.
6. **Discover relationships** - link related memories across sessions.

## Procedure

1. `memory action=list scope=all limit=300`. Read everything before changing anything.
2. Back up first: `cp ~/.jcode/memory/global.json ~/.jcode/memory/global.pregarden.bak`
   and the same for `~/.jcode/memory/projects/*.json`.
3. Cluster the entries by topic. A cluster of 5+ near-identical fragments about
   one subject is the highest-value target.
4. For each cluster, write ONE consolidated memory that:
   - Opens with an ALL-CAPS topic line and `— CONSOLIDATED (date, supersedes <ids>)`.
   - States CURRENT STATE separately from HISTORY. The reader needs to know what
     is true now, not the chronology of how you learned it.
   - Preserves every load-bearing detail: file paths, line numbers, commit SHAs,
     exact command lines, config keys, error strings. Losing these defeats the point.
   - Keeps the method traps and hard-won techniques. Those are the most valuable
     content in any memory and are the first thing lost in a careless merge.
   - Marks open plans/TODOs explicitly so they are not mistaken for done work.
5. **Verify the write landed** before deleting anything. A long `remember` can
   silently return an existing id without persisting. Confirm with:
   `grep -o "CONSOLIDATED" ~/.jcode/memory/global.json | wc -l`
   or search a distinctive phrase from the new memory.
6. Only then `memory action=forget` the superseded ids.
7. Project-scoped memories live in `~/.jcode/memory/projects/<hash>.json` and the
   `forget` action may not reach them from another project. Edit those files
   directly with python/json, then re-verify the count.

## Rules

- Never delete before the replacement is confirmed persisted.
- Never merge away a `[correction]`. Corrections encode a mistake already made
  once; fold their content into the consolidated entry verbatim.
- Never store secrets, API keys, tokens, or credentials.
- Prefer fewer, denser, self-contained memories over many fragments. A memory
  that requires reading four other memories to interpret is a failed memory.
- Report a before/after count when done.

## Verification

After gardening, re-run `memory action=list scope=all` and confirm:
- No two entries describe the same subject.
- No contradictions remain unresolved.
- Every consolidated entry is readable standalone.
