## RTK — token-optimized command proxy

- Meta-commands (call directly): `rtk gain`, `rtk discover`, `rtk proxy <cmd>` (raw, unfiltered).
- Heredocs and inline one-liners (`python3 -c`, `<<EOF`) are NOT rewritten by rtk and may
  still show partial output. Prefer writing the script to a file and running it normally.
- If output looks cut off, don't re-run the same command to check — use `rtk proxy <cmd>`
  for a raw pass instead of guessing.
