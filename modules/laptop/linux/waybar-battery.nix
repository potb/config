{lib, ...}: {
  nixos = {};
  darwin = {};

  home.linux = {
    programs.waybar.settings.barA = {
      battery = {
        format = "<span font_features='tnum'>{capacity:02}%</span>";
        format-charging = "<span font_features='tnum'>{capacity:02}%+</span>";
        states = {
          warning = 30;
          critical = 15;
        };
        interval = 30;
      };

      modules-right = lib.mkOrder 1200 ["battery"];
    };

    programs.waybar.style = lib.mkAfter ''
      #battery.warning {
        color: #df8e1d;
      }

      #battery.critical {
        color: #d20f39;
      }
    '';
  };
}
