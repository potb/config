{
  pkgs,
  lib,
  ...
}: let
  # AeroSpace matches `alt` from either option key and cannot distinguish the
  # two (nikitabobko/AeroSpace#28), while qwerty-fr puts every accented and
  # typographic character behind option. Binding option directly would cost
  # the layout. Karabiner rewrites the left option key alone into the chord
  # below, which no keyboard can produce by itself, so only that key reaches
  # the window manager and the right one still types é.
  leftOptionChord = {
    key_code = "left_control";
    modifiers = ["left_command" "left_alt"];
  };
  mod = "ctrl-cmd-alt";

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
    "${mod}-h" = "split horizontal";
    "${mod}-v" = "split vertical";
    "${mod}-t" = "layout tiles accordion";
    "${mod}-s" = "layout horizontal vertical";
    "${mod}-tab" = "workspace-back-and-forth";
  };

  karabinerRule = pkgs.writeText "aerospace.json" (builtins.toJSON {
    title = "AeroSpace";
    rules = [
      {
        description = "Left option drives AeroSpace, right option keeps typing qwerty-fr";
        manipulators = [
          {
            type = "basic";
            from = {
              key_code = "left_option";
              modifiers.optional = ["any"];
            };
            to = [leftOptionChord];
          }
        ];
      }
    ];
  });
in {
  nixos = {};

  darwin = {
    services.aerospace = {
      enable = true;

      settings = {
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

        mode.main.binding =
          workspaceBindings
          // focusBindings
          // launchBindings
          // layoutBindings;
      };
    };

    # Colours come from stylix, which themes this module already.
    services.jankyborders = {
      enable = true;
      style = "round";
      width = 4.0;
      hidpi = true;
    };

    services.karabiner-elements.enable = true;
  };

  home.darwin = {config, ...}: let
    rulesDir = "${config.xdg.configHome}/karabiner/assets/complex_modifications";
  in {
    # Karabiner rewrites files under this directory whenever its own UI is
    # used, so the rule is copied in rather than symlinked to the store.
    home.activation.karabinerLeftOptionModifier = lib.hm.dag.entryAfter ["writeBoundary"] ''
      run mkdir -p ${rulesDir}
      run install -m 644 ${karabinerRule} ${rulesDir}/aerospace.json
    '';
  };
}
