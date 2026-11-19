# Editing herdr-app

Read `AGENTS.md` in this folder first: it is herdr-app's own manual, rewritten
on every start, so never edit it.

Some of this folder is owned by the config repo at
`/home/potb/projects/potb/config`:

- `mods/<name>` for the mods listed in `modules/dev/herdr/mods/` there, and
  `tools/`, are links into that repo. Edits through them change the repo's
  working tree and reload live, but they are lost unless committed there.
- Other mods, `layouts/`, `keys.json`, `settings.json` and `programs.json` are
  local to this machine and not versioned.

To keep a change to a linked mod or tool:

1. Read `/home/potb/projects/potb/config/AGENTS.md` for the repo's commit
   rules.
2. Run `herdr-app check ~/.config/herdr-app/mods/<name>` and check
   `herdr-app status` for errors.
3. Commit from `/home/potb/projects/potb/config` (`git -C` or `cd` there), so
   its hooks run.

A new mod that should persist goes in `modules/dev/herdr/mods/<name>` in the
repo, not in `mods/` here. It needs a Home Manager switch to get its link.

Never put credentials in a mod or tool. The repo's `docs/herdr.md` says where
they go.
