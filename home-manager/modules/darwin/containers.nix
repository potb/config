{pkgs, ...}: {
  home.packages = with pkgs; [
    colima
    lima
  ];
}
