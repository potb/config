{
  pkgs,
  inputs,
  lib,
  ...
}: {
  home = {
    packages = (
      with pkgs; [
        fnm
        act
        duf
        du-dust
        fd
        glow
        httpie
        nh
        eza
        bat
        ripgrep
        zoxide
        gh
        jq
        colima
        lima
        docker-client
        docker-compose
        claude-code
        stripe-cli
        git-lfs
        git-filter-repo
        ffmpeg
        bun
        uv
        python3
        python3Packages.pip
	spotify
      ]
    );

    sessionVariables = {
      EDITOR = "nvim";
    };

    stateVersion = "25.05";
  };
}
