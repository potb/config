{pkgs, ...}: {
  nixos = {
    users.users.potb = {
      isNormalUser = true;
      description = "Peïo Thibault";
      extraGroups = ["wheel"];
      shell = pkgs.zsh;
    };
  };

  darwin = {
    system.primaryUser = "potb";

    programs.zsh.enable = true;

    users.users.potb = {
      home = "/Users/potb";
      shell = pkgs.zsh;
    };
  };

  home = {};
}
