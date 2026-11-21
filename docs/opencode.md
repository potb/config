# OpenCode

`modules/agents/opencode.nix` installs the OpenCode V2 CLI from
`numtide/llm-agents.nix` as `opencode`. The upstream derivation is named
`opencode2`, so the module links its binary into a package that provides the
`opencode` command. It shares the parts of the Claude Code setup that OpenCode
can express. The file is written for OpenCode V2.

## Configuration ownership

`~/.config/opencode/opencode.json` stays a regular, writable file. The module
writes its own values to a store file and merges them into the existing file
during the `opencodeSettings` activation step, using a recursive `jq` merge.
Keys the module sets win. Keys it does not set, such as the provider
credentials and the Honcho and browse MCP servers, keep their current values.

Nix owns these keys:

- `$schema`
- `model`
- `skills`
- `providers.claude-agent`
- `providers.vercel-ai`
- `policies`
- `agents.build.model`
- `agents.plan.disabled`
- `compaction.buffer`
- `permissions`
- `mcp.servers.sentry`
- `mcp.servers.desktop`

`~/.config/opencode/cli.json` stays a regular file. The module merges
`modules/agents/opencode/cli.json` into it during the `opencodeCliSettings`
activation step. A direct `mkOutOfStoreSymlink` does not survive here: OpenCode
rewrites the file when it normalizes CLI settings. Nix owns `theme`,
`diffs.wrap`, `session.sidebar`, `session.scrollbar`, `session.thinking`,
`animations` and `tabs.mode`. The merged file sets the Catppuccin theme,
word-wrapped diffs, hidden thinking output and tabs off.

The merge cannot remove a key on its own. Deleting one of the keys above from
the module leaves its last value in the file until someone removes it by hand,
the same behaviour as the Claude settings activation.

Before merging, `opencodeSettings` deletes the keys listed in
`legacySettingsKeys`: the V1 `provider` and `agent` blocks, the
`providers.claude` and `providers.vercel` entries OpenCode normalized out of
them, and `agents.plan.model`, which pointed at a retired `anthropic/...`
model. Add a key to that list when the module stops setting it.

## Legacy V1 install

OpenCode V2 also reads `~/.opencode/opencode.json` as a global config source.
The V1 install left a binary, a `node_modules` tree and a `/review` command
there; the command ran four parallel subagents through `delegate_task`, a tool
V2 does not have. Nix does not manage `~/.opencode`, so it was removed by hand.
If it reappears, `opencode debug config` lists it among the sources.

## Shared Claude settings

| Claude Code setting | OpenCode equivalent |
| --- | --- |
| `model = "claude-opus-5-5"` | `model = "claude-agent/opus"` |
| `modelSettings.<model>.effortLevel = "medium"` | `settings.effort = "medium"` on Sonnet and Opus |
| `autoCompactWindow = 400000` | `compaction.buffer = 600000` tokens |
| `~/.claude/CLAUDE.md` | `~/.config/opencode/AGENTS.md` |
| `~/.claude/skills` | explicit `skills` entry, alongside automatic discovery |
| Sentry and desktop MCP servers | the same servers under `mcp.servers` |

The compaction value mirrors the Claude threshold on a 1M token model:
OpenCode's `buffer` is the room kept free, so 600000 free tokens compacts at
400000 used tokens. For a model with a smaller window, a buffer at least as
large as the window is ignored and the OpenCode default applies.

`~/.config/opencode/AGENTS.md` is a symlink to the same
`modules/agents/claude/CLAUDE.md` source as `~/.claude/CLAUDE.md`. OpenCode
loads a global `AGENTS.md` instead of falling back to the global `CLAUDE.md`,
so the file is loaded once rather than twice.

`skills = ["~/.claude/skills"]` makes the sharing explicit. OpenCode also
discovers that directory on its own.

The desktop MCP server comes from `computer-use-linux` on Linux and from
`mac-mcp-server` through `npx` on macOS, matching the Claude module.

## Model catalog

The module curates the model selector to five entries through a generated
plugin.

The Claude entries use the built-in `claude-agent` provider directly, with its
display name overridden to `Claude`. They cannot be cloned into a custom
provider: the provider package is the internal `aisdk:@opencode/claude-agent`
and a custom provider tries to install it from npm, which returns 404. The four
entries are the provider's stable latest aliases, so they follow new releases
without a configuration change. The selector shows only the family name:
Haiku, Sonnet, Opus or Fable, with no version number.

`vercel-ai/deepseek-v4.1` is a custom provider with `canonical = "vercel"`. The
model ID is an alias for the gateway's `deepseek/deepseek-v4.1-flash-fast` and
inherits its limits, costs and variants. The selector shows DeepSeek Flash
Fast, with the version kept only in `modelID`. The provider ID must differ from
its canonical ID: reusing `vercel` still lists the whole gateway catalog.

`modelAllowlist` in the module feeds a generated
`~/.config/opencode/plugins/model-allowlist.ts`, linked with `home.file`. It
removes every model outside the five listed references, so a newly published
catalog model does not leak into the selector. `policies` then denies every
provider except `claude-agent` and `vercel-ai`, which also hides the `opencode`
free and Console models and the raw `anthropic` and `vercel` providers.

Default reasoning effort is set on the model entries. `deepseek-v4.1` uses
`reasoningEffort = "high"`, while `sonnet` and `opus` use `effort = "medium"`.
An explicit `#variant` in a model reference still takes precedence.

The model selector sorts by release date descending, then by name. The Claude
entries carry assigned dates that order them by capability: Fable, Opus, Sonnet,
Haiku. Those dates only drive the selector order; they are not the upstream
release dates.

Model references are `claude-agent/<alias>` and `vercel-ai/deepseek-v4.1`.
Sessions started with `anthropic/claude-opus-5-5` or `vercel/...` do not resolve
after the change. The Claude provider uses the connected Claude Agent account.
The Vercel provider reads its key from
`~/.config/herdr-app/data/ai-spend/vercel.key`.

## Comment guard

Claude Code and OpenCode share one comment guard,
`modules/agents/claude/hooks/comment-guard.py`. It never blocks a tool call. It
runs after an edit and, when the edit added code comments, tells the agent which
ones so it removes them. Tool directives such as `eslint-disable` or `noqa` are
not reported.

- Claude Code runs it as a `PostToolUse` hook on `Edit`, `MultiEdit`, `Write`
  and `Bash`, and the notice arrives as `additionalContext`.
- OpenCode runs it from the generated
  `~/.config/opencode/plugins/comment-guard.ts`, on `execute.after` for `edit`,
  `write`, `patch` and `shell`. The plugin translates the call into the Claude
  hook payload and posts the notice into the session with `session.synthetic`.

A shell command that writes files (an in-place `sed` or `perl`, a redirect, a
heredoc, `tee`, or an inline interpreter script) is allowed too. The guard
scans the lines it added: `git diff HEAD` for a tracked file, the whole file
for an untracked one. When it cannot tell which files the command wrote, it
asks the agent to check `git diff` itself.

## Agents

The built-in `plan` agent is disabled. `build` is the only primary agent left.
The `general` and `explore` subagents remain available.

## Claude settings with no OpenCode equivalent

These are intentionally not translated:

- `permissions.defaultMode = "auto"` uses a Claude Code classifier before
  actions run. OpenCode has ordered permission rules and a client-side
  `autoaccept` setting, which either asks or blindly accepts, but no classifier.
  Enabling `autoaccept` would therefore be broader than auto mode.
- `outputStyle = "Concise"` has no output style setting. The shared
  instructions carry the writing rules instead.
- `enableWorkflows`, `ultracode`, `skipWorkflowUsageWarning`,
  `remoteControlAtStartup`, `promptSuggestionEnabled`,
  `inputNeededNotifEnabled` and `agentPushNotifEnabled` describe Claude Code
  features that OpenCode does not have.
- `worktree.baseRef = "fresh"` has no OpenCode setting. OpenCode only chooses
  where worktrees live, through `worktree.directory`.
- `tui = "fullscreen"` is the normal OpenCode TUI.
- `theme = "light"` lives in the managed `cli.json`, which sets the Catppuccin
  theme in light mode.
- Notification settings could map to `attention.notifications` in the managed
  `cli.json`.

## Skills

The `stop-slop` skill works in OpenCode unchanged. Its Claude-only
`allowed-tools` frontmatter is ignored.

The `workflow-blocks` skill is blocked by a permission rule in OpenCode. It
documents Claude's `Workflow` tool, and advertising it to an agent that cannot
call that tool would be misleading. The skill file stays shared, so removing
the deny rule is enough if OpenCode gains an equivalent.

The herdr skill is installed separately by `modules/dev/herdr.nix`; see
[docs/herdr.md](herdr.md).

## Validating a change

Build the affected host:

```bash
nix build .#nixosConfigurations.charon.config.system.build.toplevel
```

After a Home Manager switch, OpenCode reloads config without a restart. Run
`opencode debug config` to see the merged sources.
