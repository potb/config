{
  pkgs,
  lib,
  ...
}: let
  chordModifiers = ["left_control" "left_command" "left_option"];
  mod = "ctrl-cmd-alt";

  karabinerKeyCodes =
    lib.genAttrs workspaces lib.id
    // lib.genAttrs ["p" "w" "f" "h" "v" "t" "s" "tab"] lib.id
    // {
      left = "left_arrow";
      right = "right_arrow";
      up = "up_arrow";
      down = "down_arrow";
      enter = "return_or_enter";
      backspace = "delete_or_backspace";
      space = "spacebar";
    };

  workspaces = map toString (lib.range 1 9) ++ ["0"];
  workspaceBindings = lib.listToAttrs (
    lib.concatMap (workspace: [
      (lib.nameValuePair "${mod}-${workspace}" "workspace ${workspace}")
      (lib.nameValuePair "${mod}-shift-${workspace}" "move-node-to-workspace ${workspace}")
    ])
    workspaces
  );

  focusBindings = lib.listToAttrs (
    lib.concatMap (direction: [
      (lib.nameValuePair "${mod}-${direction}" "focus ${direction}")
      (lib.nameValuePair "${mod}-shift-${direction}" "move ${direction}")
    ])
    ["left" "right" "up" "down"]
  );

  launchBindings = {
    "${mod}-enter" = "exec-and-forget open -na Ghostty";
    "${mod}-p" = "exec-and-forget open -a Raycast";
    "${mod}-w" = "exec-and-forget open -a 'Google Chrome'";
  };

  # hy3 groups windows explicitly, where AeroSpace reaches the same
  # arrangement by reorienting the container the focused window sits in, so
  # these commands read differently from their Hyprland counterparts.
  layoutBindings = {
    "${mod}-backspace" = "close";
    "${mod}-f" = "fullscreen";
    "${mod}-space" = "layout floating tiling";
    # AeroSpace refuses to load a config that pairs `split` with the flatten
    # normalization enabled above, because flattening undoes the container
    # the split creates. Setting the orientation of the container the window
    # already sits in survives normalization and arranges the same way.
    "${mod}-h" = "layout h_tiles";
    "${mod}-v" = "layout v_tiles";
    "${mod}-t" = "layout tiles accordion";
    "${mod}-s" = "layout horizontal vertical";
    "${mod}-tab" = "workspace-back-and-forth";
  };

  bindings =
    workspaceBindings
    // focusBindings
    // launchBindings
    // layoutBindings;

  boundKeys = lib.unique (map (binding: lib.last (lib.splitString "-" binding)) (lib.attrNames bindings));

  retiredRuleDescriptions = [
    "Left option drives AeroSpace, right option keeps typing qwerty-fr"
  ];

  terminalAltVariable = "right_command_is_terminal_alt";

  terminalBundleIdentifiers = ["^com\\.mitchellh\\.ghostty$"];

  karabinerRule = pkgs.writeText "aerospace.json" (builtins.toJSON {
    title = "AeroSpace";
    rules = [
      {
        description = "Right command is a plain alt in the terminal, never an AeroSpace chord or an accent";
        manipulators = [
          {
            type = "basic";
            from = {
              key_code = "right_command";
              modifiers.optional = ["any"];
            };
            to = [
              {
                set_variable = {
                  name = terminalAltVariable;
                  value = 1;
                };
              }
              {key_code = "left_option";}
            ];
            to_after_key_up = [
              {
                set_variable = {
                  name = terminalAltVariable;
                  value = 0;
                };
              }
            ];
            conditions = [
              {
                type = "frontmost_application_if";
                bundle_identifiers = terminalBundleIdentifiers;
              }
            ];
          }
        ];
      }
      {
        description = "Left option plus an AeroSpace key sends the AeroSpace chord, right option keeps typing qwerty-fr";
        manipulators =
          map (key: let
            code = karabinerKeyCodes.${key} or (throw "aerospace.nix: no Karabiner key code for AeroSpace key `${key}`");
          in {
            type = "basic";
            from = {
              key_code = code;
              modifiers = {
                mandatory = ["left_option"];
                optional = ["any"];
              };
            };
            to = [
              {
                key_code = code;
                modifiers = chordModifiers;
              }
            ];
            conditions = [
              {
                type = "variable_unless";
                name = terminalAltVariable;
                value = 1;
              }
            ];
          })
          boundKeys;
      }
    ];
  });
in {
  nixos = {};

  darwin = {
    services.aerospace = {
      enable = true;

      settings = {
        config-version = 2;
        persistent-workspaces = workspaces;

        enable-normalization-flatten-containers = true;
        enable-normalization-opposite-orientation-for-nested-containers = true;

        default-root-container-layout = "tiles";
        default-root-container-orientation = "auto";

        # Hiding an app leaves macOS focused on a window the layout can no
        # longer show.
        automatically-unhide-macos-hidden-apps = true;

        gaps = {
          inner = {
            horizontal = 10;
            vertical = 10;
          };
          outer = {
            left = 5;
            right = 5;
            top = 5;
            bottom = 5;
          };
        };

        mode.main.binding = bindings;
      };
    };

    # Colours come from stylix, which themes this module already.
    services.jankyborders = {
      enable = true;
      style = "round";
      width = 4.0;
      hidpi = true;
    };
  };

  home.darwin = {config, ...}: let
    karabinerDir = "${config.xdg.configHome}/karabiner";

    # Listing a rule under assets only offers it in the UI, so the profile
    # has to carry a copy of it to be in effect. Karabiner owns this file and
    # rewrites it whenever its settings change, which rules out both a store
    # symlink and home.file, so the rule is merged into whatever is there and
    # matched by description to stay idempotent.
    mergeRule = pkgs.writeShellScript "karabiner-merge-aerospace-rule" ''
      set -euo pipefail

      config="${karabinerDir}/karabiner.json"
      rule=${karabinerRule}
      retired='${builtins.toJSON retiredRuleDescriptions}'

      if [ ! -e "$config" ]; then
        ${lib.getExe pkgs.jq} -n --slurpfile rule "$rule" '{
          profiles: [{
            name: "Default profile",
            selected: true,
            virtual_hid_keyboard: {keyboard_type_v2: "ansi"},
            complex_modifications: {rules: $rule[0].rules},
          }],
        }' > "$config"
        exit 0
      fi

      merged=$(${lib.getExe pkgs.jq} --slurpfile rule "$rule" --argjson retired "$retired" '
        .profiles |= map(
          .complex_modifications.rules = (
            ((.complex_modifications.rules // []) | map(select(
              .description as $existing
              | ($rule[0].rules | map(.description) + $retired | index($existing)) == null
            )))
            + $rule[0].rules
          )
        )
      ' "$config")

      if [ "$merged" != "$(cat "$config")" ]; then
        printf '%s\n' "$merged" > "$config"
      fi
    '';
  in {
    home.activation.karabinerLeftOptionModifier = lib.hm.dag.entryAfter ["writeBoundary"] ''
      run mkdir -p ${karabinerDir}/assets/complex_modifications
      run install -m 644 ${karabinerRule} ${karabinerDir}/assets/complex_modifications/aerospace.json
      run ${mergeRule}
    '';
  };
}
