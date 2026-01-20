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
        fzf
        glow
        httpie
        nh
        eza
        bat
        ripgrep
        zoxide
        gh
        jq
        tokei
        bottom
        htop

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
        awscli2

        # LSP servers
        nil
        typescript-language-server
        python3Packages.python-lsp-server

        # Formatters
        nixfmt
        python3Packages.black

        # Notifications
        claude-notify

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
