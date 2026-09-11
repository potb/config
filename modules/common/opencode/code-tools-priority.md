## Code exploration/analysis tool priority

Three code-graph MCPs are available; they are NOT interchangeable — pick by task:

1. `codegraph_explore` — DEFAULT for reading/understanding code. One call returns
   verbatim source + call paths for the relevant symbols. Use for "how does X work",
   "show me Y before I edit it", architecture questions, bug investigation.
2. `code-analytics_search_code` — fallback for pattern/string search across many
   files when you don't have a symbol name yet (grep-like, graph-ranked results).
   Use only if `codegraph_explore` doesn't surface what you need.
3. `Read` / `Grep` / `Glob` — last resort, for anything neither graph tool resolves
   (configs, non-code files, or a specific detail codegraph missed).

Do not start with Read/Grep/Glob for code understanding — always try `codegraph_explore` first.

## When to reach for the other two, specialized tools

- `code-impact` (git-aware entity intelligence) — pre-edit blast-radius ("what
  breaks if I change X": `code-impact_impact`) and git-aware history
  (`code-impact_log`, `code-impact_blame`, `code-impact_diff`). Use before editing
  a symbol you didn't write, or when asked "why is this shaped this way" / "who
  changed this".
- `code-analytics` (architecture metrics) — aggregate analysis: clusters, layers,
  boundaries, complexity/hotpath detection via Cypher (`code-analytics_query_graph`),
  semantic search. Use for architecture reviews, finding complexity hotspots, or
  cross-repo route matching — not for routine "find/read this function" tasks.
