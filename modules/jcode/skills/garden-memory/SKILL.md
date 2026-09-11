---
name: garden-memory
description: Use when asked to garden, consolidate, prune, or clean up memories. Maintains the memory graph - merges duplicates, resolves contradictions, prunes dead memories, verifies stale facts, and extracts from missed sessions.
allowed-tools: memory, bash, read, write, batch, todo, session_search
---

# Garden Memory

Full graph-wide memory consolidation. This is the interactive version of the
ambient garden cycle defined in `crates/jcode-app-core/src/ambient/prompt.rs`.

## How the store actually works

Read this before changing anything. The procedure below depends on it.

- Stores are single-line JSON: `~/.jcode/memory/global.json` and
  `~/.jcode/memory/projects/<hash>.json`. Read-modify-write them with python.
  Never sed, never assume pretty printing.
- `MemoryEntry` carries `active: bool` and `superseded_by: Option<String>`.
  Every read path honours them: prompt injection filters on `entry.active`
  (`selected_entries_for_prompt`), and semantic recall iterates
  `active_memories()`. Setting `active=false` removes an entry from the model's
  view while keeping the node, its edges, and its history on disk.
- `memory action=forget` is a hard delete. `remove_memory` drops the node and
  both edge directions, decrements tag counts, and leaves no tombstone. Use it
  only for genuine garbage, never for consolidation.
- `EdgeKind::Supersedes` exists in the graph schema and serialises as
  `{"target": "<old_id>", "kind": "supersedes"}`. Provenance belongs there, not
  in the memory text.
- `remember` deduplicates at cosine >= 0.85: it returns the *existing* id,
  reinforces it, and never writes your new text, while printing the same
  `Remembered ...` line as a real write. Always check the returned id against
  the ids you listed before the write.
- `forget` only reaches the current project graph plus global, so project ids
  from another working directory are unreachable through the tool. Editing the
  JSON works from anywhere.
- Saving a store hard-links the previous version to `<name>.bak`, so plain
  `.bak` is overwritten on every write. Back up under a distinct name.
- The writer keeps a process-level graph cache keyed on mtime. External edits
  are picked up, but a running session that saves after your edit will overwrite
  it. Garden while the target project has no active session.

## Priority order

Highest value first. Duplicates and contradictions before pruning. Verify stale
facts only if budget remains.

1. **Consolidate duplicates** - semantically similar memories merge into one
   authoritative entry, and the sources are retired rather than deleted.
2. **Resolve contradictions** - when two memories disagree, determine which is
   true, write the corrected version, retire the wrong one. Never leave both
   active.
3. **Prune dead memories** - superseded entries, one-off session trivia,
   completed TODOs, weak memories (confidence < 0.05 AND strength <= 1).
4. **Verify stale facts** - check factual memories against the actual codebase
   or filesystem. Facts about file paths, config values, and test status rot fast.
5. **Extract from missed sessions** - use `session_search` for recent work not
   yet reflected in memory.
6. **Discover relationships** - link related memories across sessions.

## Procedure

1. `memory action=list scope=all limit=300`. Read everything before changing
   anything. Keep the id list; step 5 needs it.
2. Back up under a name the writer will not clobber:
   `cp ~/.jcode/memory/global.json ~/.jcode/memory/global.pregarden.bak`
   and the same for `~/.jcode/memory/projects/*.json`.
3. Cluster the entries by topic. A cluster of 5+ near-identical fragments about
   one subject is the highest-value target.
4. For each cluster, write ONE consolidated memory that:
   - Opens with an ALL-CAPS topic line. No id list, no date, no `CONSOLIDATED`
     banner: that provenance goes into the graph in step 6, where it stays
     machine-readable and costs no prompt tokens.
   - States CURRENT STATE separately from HISTORY. The reader needs to know what
     is true now, not the chronology of how you learned it.
   - Preserves every load-bearing detail: file paths, line numbers, commit SHAs,
     exact command lines, config keys, error strings. Losing these defeats the point.
   - Keeps the method traps and hard-won techniques. Those are the most valuable
     content in any memory and are the first thing lost in a careless merge.
   - Marks open plans/TODOs explicitly so they are not mistaken for done work.
5. **Verify the write landed.** If the id returned by `remember` already appears
   in the step 1 list, the dedup path swallowed the write and nothing was
   persisted. Reword the entry or edit the existing id in place instead.
6. Retire the sources. In the store JSON, for each superseded id:
   - `m["active"] = False`
   - `m["superseded_by"] = "<new_id>"`
   - append `{"target": "<old_id>", "kind": "supersedes"}` to `edges[<new_id>]`
     and `<new_id>` to `reverse_edges[<old_id>]`.

   The entries leave the prompt immediately, keep their tags and edges, and can
   be restored by flipping `active` back.
7. Tag the consolidated entry with `memory action=tag id=<new_id>
   tags=["consolidated"]` if a visible marker is wanted. Tags are structured,
   greppable, and stay out of the prompt body.
8. Refresh `search_text` on any entry whose content you edited. It is the
   lexical index and is not recomputed on load. The normalisation is: trim,
   lowercase, then map whitespace and `-` `_` `/` `\` `.` `:` to single spaces.
9. Leave `embedding` untouched when editing content in place. Clearing it drops
   the entry out of semantic recall until something regenerates it, and the only
   backfill runs at the end of an ambient cycle.

## Rules

- Never delete before the replacement is confirmed persisted.
- Prefer retiring (`active=false` plus `superseded_by`) over `forget`. Reserve
  `forget` for entries with no historical value at all.
- Never merge away a `[correction]`. Corrections encode a mistake already made
  once; fold their content into the consolidated entry verbatim.
- Never store secrets, API keys, tokens, or credentials.
- Prefer fewer, denser, self-contained memories over many fragments. A memory
  that requires reading four other memories to interpret is a failed memory.
- Report a before/after count when done, split into active and retired.

## Verification

After gardening, re-run `memory action=list scope=all` and confirm:
- No two active entries describe the same subject.
- No contradictions remain unresolved.
- Every consolidated entry is readable standalone.
- Every retired entry has a `superseded_by` pointing at a node that exists.
