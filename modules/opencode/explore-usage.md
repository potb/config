## Delegating to the `explore` subagent

`explore` is a read-only locator, not an analyst. It returns `path:line` + verbatim
snippets as evidence — never conclusions.

- Give it ONE narrow, concrete target. Good: "find all call sites of `parseConfig`
  and the file that defines it." Bad: "how does config loading work?"
- Ask for locations + snippets, then draw conclusions YOURSELF from the cited evidence.
- State thoroughness: quick / medium / very thorough.
- Fire multiple explore calls in parallel for independent targets.
- Trust its citations — do not re-verify a `path:line` it already quoted. `NOT FOUND`
  or "No conclusion drawn" is expected behavior: read the evidence and decide, or send
  a narrower follow-up.
- Never ask it to decide whether to edit, judge quality, or explain "why/should" —
  that is your job.
