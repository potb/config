{pkgs, ...}: {
  nixos = {
    environment.systemPackages = [pkgs.brightnessctl];

    services.logind.settings.Login = {
      HandleLidSwitch = "suspend";
      HandleLidSwitchExternalPower = "suspend";
      HandleLidSwitchDocked = "ignore";
    };

    systemd.sleep.settings.Sleep.AllowHibernation = "no";
  };

  darwin = {};

  home.linux = {
    wayland.windowManager.hyprland.settings.bindl = [
      ", XF86MonBrightnessUp, exec, ${pkgs.brightnessctl}/bin/brightnessctl set +10%"
      ", XF86MonBrightnessDown, exec, ${pkgs.brightnessctl}/bin/brightnessctl set 10%-"
    ];
  };
}
