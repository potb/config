# Upstream warnings

`scripts/flake-check` treats every evaluation warning as a failure. That is
deliberate: a warning here is almost always a renamed option or a deprecation
that will become an error at the next input bump, and it should be fixed rather
than scrolled past.

Some warnings cannot be fixed from this repo, because an input emits them about
its own configuration. For those, `checks.kerberos-offhost` in `flake.nix`
carries an `acknowledgedUpstreamWarnings` list. An entry silences one warning and
records why.

The list is not a mute button. Each entry must still match a warning that is
actually emitted; once upstream fixes the warning, the check fails with a stale
acknowledgement error and the entry has to be deleted. So the list can only ever
shrink on its own, and it never hides a warning that has started meaning
something new.

Add an entry only when all of the following hold:

- the warning comes from an input, not from a module in this repo
- the option it names is not set anywhere in this repo
- upstream has no released fix yet

Otherwise, fix the configuration instead.

## Current entries

### `programs.rofi.font`

Stylix sets `programs.rofi.font` in its own rofi target, and home-manager has
renamed that option to `programs.rofi.settings.font`. Nothing in this repo sets
it: the only rofi configuration here is `programs.rofi.enable = true` in
`modules/gui/linux/rofi.nix`.

The fix belongs in stylix, which still sets the old name on master as of
2026-09-17. The alternatives were both worse than acknowledging it:

- `stylix.targets.rofi.enable = false` also drops the colour theme, so rofi
  would stop matching the rest of the desktop.
- Setting `programs.rofi.settings.font` here does not help, because the warning
  fires on stylix's definition of the old option, not on the resulting value.

Remove the entry once a stylix bump stops emitting the warning. The check will
say so.
