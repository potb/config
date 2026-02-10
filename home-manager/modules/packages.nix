{pkgs, ...}: {
  programs.eza = {
    enable = true;
    enableZshIntegration = true;
  };

  programs.bat.enable = true;
  programs.ripgrep.enable = true;

  programs.gh = {
    enable = true;
    settings = {
      git_protocol = "ssh";
      prompt = "enabled";
      pager = "${pkgs.bat}/bin/bat";
    };
  };

  programs.jq.enable = true;

  home.packages = with pkgs; [
    fd
    fzf
    duf
    dust
    glow
    httpie
    tokei
    bottom
    htop
    nh
    act
    ffmpeg
    lefthook
  ];

  home.sessionVariables.EDITOR = "nvim";
  home.stateVersion = "25.05";
}
