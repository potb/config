# Claude Code settings

`modules/agents/claude.nix` writes `~/.claude/settings.json` during the
home-manager activation step `claudeSettings`. The file stays a regular,
writable file so Claude Code can save settings changed through `/config` or
`/model`.

Activation merges the Nix settings into the existing file with a deep `jq`
merge (`.[0] * .[1]`). Keys set in Nix win; keys only present in the file are
kept. A key removed from Nix therefore stays in the file until it is removed by
hand.

`hooks` is the exception: Nix owns it entirely and activation replaces the
whole object. Hooks reference Nix store paths, so a hook that Nix no longer
declares would otherwise point at a path that garbage collection eventually
deletes. This also drops any hook a plugin or `/hooks` wrote into the file, such
as the jcode `SessionStart` hooks that used to need their own cleanup step.
Declare every hook in `settings.hooks`.

`autoCompactWindow` is set at the top level so it applies to every model. A
`modelSettings.<model>.autoCompactWindow` entry, which `/autocompact` writes,
would take precedence over it for that model, so activation deletes those
entries. A window changed with `/autocompact` lasts until the next activation.

Plugin state (`enabledPlugins`, `extraKnownMarketplaces`) is left to Claude
Code and lives only in the file.
