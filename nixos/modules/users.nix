{pkgs, ...}: {
  users.users.potb = {
    isNormalUser = true;
    description = "Peïo Thibault";
    extraGroups = [
      "wheel"
      "i2c"
    ];
    shell = pkgs.zsh;
  };
}
