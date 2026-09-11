{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};
  home = {
    programs.gh = {
      enable = true;
      settings = {
        git_protocol = "ssh";
        prompt = "enabled";
        pager = "${pkgs.bat}/bin/bat";
      };
    };

    home.packages = with pkgs;
      [
        tokei
        act
        lefthook
        _1password-cli
        hyperfine
        yt-dlp
        ffmpeg

        ast-grep
        (d2.override {withImageSupport = false;})
        shellcheck
        shfmt
        tectonic

        duckdb
        harlequin
        postgresql_18

        glab
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isLinux [
        gcc
        binutils
        gnumake
        lm_sensors
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isDarwin [
        stdenv.cc

        macmon
        mactop

        mermaid-cli
        firebase-tools
        gitlab-ci-local
        google-cloud-sdk
        terraform
      ];
  };
}
