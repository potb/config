{pkgs, ...}: {
  # macOS needs colima/lima for Docker
  home.packages = with pkgs; [
    colima
    lima
  ];
}
