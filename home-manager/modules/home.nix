{
  pkgs,
  inputs,
  lib,
  ...
}: {
  home = {
    packages = (
      with pkgs; [
        # CLI tools
        fnm
        act
        duf
        dust
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

        # Docker
        colima
        lima
        docker-client
        docker-compose

        # Build tools
        (lib.hiPrio clang)
        gnumake
        pkg-config

        # Editors & IDEs
        jetbrains.datagrip

        # Zed editor wrapped with claude-code for Claude Code integration
        (pkgs.symlinkJoin {
          name = "zed-editor-wrapped";
          paths = [pkgs.zed-editor];
          buildInputs = [pkgs.makeWrapper];
          postBuild = ''
            wrapProgram $out/bin/zeditor \
              --prefix PATH : ${pkgs.lib.makeBinPath [pkgs.claude-code]}
          '';
        })

        # Development tools
        claude-code
        stripe-cli
        git-lfs
        git-filter-repo
        ffmpeg
        bun
        deno
        uv
        python3
        python3Packages.pip

        # Applications
        spotify
        google-chrome
        slack
        discord
      ]
    );

    sessionVariables = {
      EDITOR = "nvim";
    };

    stateVersion = "25.05";
  };
}
