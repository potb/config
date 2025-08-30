{pkgs, ...}: {
  system.primaryUser = "potb";

  programs.zsh.enable = true;

  users.users.potb = {
    home = "/Users/potb";
    shell = pkgs.zsh;
  };
}
