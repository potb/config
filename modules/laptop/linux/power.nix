{
  lib,
  pkgs,
  ...
}: let
  lockedExec = key: command: {
    _args = [
      key
      (lib.generators.mkLuaInline "hl.dsp.exec_cmd(${builtins.toJSON command})")
      {locked = true;}
    ];
  };
in {
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
    wayland.windowManager.hyprland.settings.bind = [
      (lockedExec "XF86MonBrightnessUp" "${pkgs.brightnessctl}/bin/brightnessctl set +10%")
      (lockedExec "XF86MonBrightnessDown" "${pkgs.brightnessctl}/bin/brightnessctl set 10%-")
    ];
  };
}
