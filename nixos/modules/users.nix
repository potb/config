{pkgs, ...}: {
  users.users.potb = {
    isNormalUser = true;
    description = "Peïo Thibault";
    extraGroups = ["wheel"];
    shell = pkgs.zsh;
  };
}
