# Agent rules for the config repo

This repo (`~/projects/potb/config`) is the NixOS and nix-darwin configuration
for charon, kerberos and nyx. [README.md](README.md) covers hosts, rebuilds and
layout; `docs/` holds one page per topic.

## Committing

- Run git from this directory, so the lefthook pre-commit hooks run:
  `nix fmt` on staged `.nix` files and `scripts/flake-check`. Fix a failing
  hook rather than skipping it.
- A commit is one conventional subject line and nothing else, for example
  `feat(herdr): add the ship sidebar`. No body, no `Co-Authored-By`, no
  session or "Generated with" trailers, even when a tool supplies them.
- Stage only the files of the change at hand. Files the flake reads must be
  tracked by git, or evaluation does not see them.
- Commit on `master` unless the owner asks for a branch. Do not push unless
  asked.

## Writing code here

- Code carries no explanatory comments. A hook rejects them. Put the
  explanation in the matching page under `docs/` and make the code read on its
  own.
- Edit files with the editor tools, not `sed -i` or scripts that rewrite
  files. A hook rejects those too.
- Before saying a change works, build the affected host, for example
  `nix build .#nixosConfigurations.charon.config.system.build.toplevel`.
  Activating it (`nh os switch`) needs the owner's sudo password.

## herdr-app mods and tools

`~/.config/herdr-app/mods/<name>` and `~/.config/herdr-app/tools` are links to
`modules/dev/herdr/mods/<name>` and `modules/dev/herdr/tools` in this repo.
Editing through either path changes the files here, and herdr-app reloads the
mod within about a second. A change persists only once it is committed here.
Credentials never go in these files: see the Credentials section of
[docs/herdr.md](docs/herdr.md), which also covers what is and is not linked.
