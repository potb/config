{pkgs, ...}: {
  users.users.potb = {
    description = "Peïo Thibault";
    shell = pkgs.zsh;
    home = "/Users/potb";
  };
}