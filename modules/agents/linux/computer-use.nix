{pkgs, ...}: {
  nixos = {
    programs.ydotool.enable = true;
    hardware.uinput.enable = true;
    services.gnome.at-spi2-core.enable = true;
    users.users.potb.extraGroups = ["ydotool" "uinput"];
  };

  darwin = {};

  home = {
    home.packages = [pkgs.computer-use-linux pkgs.wtype];

    dconf.settings."org/gnome/desktop/interface".toolkit-accessibility = true;
  };
}
