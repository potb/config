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

None.

## Worked around in this repo

### `programs.rofi.font`

Stylix's rofi target still sets `programs.rofi.font`, which home-manager has
renamed to `programs.rofi.settings.font`. Stylix generates a toggle for each
argument a target uses, so `modules/gui/theme.nix` turns off only the font part
with `stylix.targets.rofi.fonts.enable = false` on every platform, since the
target emits the warning on darwin too, and `modules/gui/linux/rofi.nix` sets
`programs.rofi.settings.font` from `config.stylix.fonts` itself. Rofi keeps the
stylix colour theme.

Drop the workaround once stylix sets the new option name.
