{pkgs, ...}: let
  opencodeBinPath = pkgs.lib.makeBinPath [
    pkgs.typescript
    pkgs.typescript-language-server
    pkgs.pyright
    pkgs.nixd
    pkgs.vscode-langservers-extracted
  ];
  opencode-wrapped = pkgs.symlinkJoin {
    name = "opencode";
    paths = [pkgs.opencode];
    nativeBuildInputs = [pkgs.makeWrapper];
    postBuild = ''
      wrapProgram $out/bin/opencode \
        --prefix PATH : ${opencodeBinPath} \
        --set-default OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS true
    '';
  };
  idea-vmoptions = pkgs.writeText "idea64.vmoptions" ''
    -Dawt.toolkit.name=WLToolkit
  '';
  idea-wrapped = pkgs.symlinkJoin {
    name = "idea";
    paths = [pkgs.jetbrains.idea];
    nativeBuildInputs = [pkgs.makeWrapper];
    postBuild = ''
      wrapProgram $out/bin/idea \
        --set-default IDEA_VM_OPTIONS ${idea-vmoptions}
    '';
  };
in {
  nixos = {};
  darwin = {};

  home = {
    programs.ghostty = {
      enable = true;
      package =
        if pkgs.stdenv.hostPlatform.isDarwin
        then pkgs.ghostty-bin
        else pkgs.ghostty;
      settings = {
        confirm-close-surface = false;

        # Stylix only sets the family, which resolves to Regular (400). Retina
        # is FiraCode's 450 weight: slightly heavier than Regular without
        # reaching Medium.
        font-style = "Retina";
        window-decoration = false;

        # On macOS Ghostty keeps running after the last window closes. Quit
        # with the last window instead, like on Linux.
        quit-after-last-window-closed = true;

        # Ghostty renders SGR 2 (faint) by blending the glyph toward the
        # background, which washes out styles like Starship's "green dimmed
        # bold" hostname. Alacritty ignored faint entirely, so keep the
        # colors at full strength to match.
        faint-opacity = 1.0;

        # Ghostty advertises TERM=xterm-ghostty, which ssh forwards verbatim to
        # hosts that have no such terminfo entry. Readline then cannot emit a
        # clear, so Ctrl-L (and anything else needing a capability lookup) dies
        # on a remote shell. ssh-terminfo installs the entry on first connect;
        # ssh-env downgrades TERM to xterm-256color for hosts where installing
        # it fails, such as a read-only or non-interactive login.
        shell-integration-features = "cursor,no-sudo,title,ssh-env,ssh-terminfo,path";
      };
    };

    home.packages = [
      idea-wrapped
      opencode-wrapped
    ];
  };
}
