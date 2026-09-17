{
  pkgs,
  lib,
  ...
}: {
  packages = ["_1password-cli"];

  nixos = {};
  darwin = {};
  home = {
    config,
    lib,
    ...
  }: {
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
        (lib.hiPrio clang)
        gnumake
        autoconf
        automake
        libtool
        pkg-config

        fnm
        bun
        uv
        python3

        nixfmt
        python3Packages.black
        sccache

        tokei
        act
        lefthook
        hyperfine
        yt-dlp
        ffmpeg

        ast-grep
        (d2.override {withImageSupport = false;})
        shellcheck
        shfmt
        tectonic

        postgresql_18

        glab
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isLinux [
        gcc
        binutils
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

    home.activation.ensureFnmDefaultAlias = lib.hm.dag.entryAfter ["writeBoundary"] ''
      fnm_dir=${config.xdg.dataHome}/fnm
      default_alias="$fnm_dir/aliases/default"

      if [ ! -e "$default_alias" ]; then
        # fnm downloads Node outside the nix store, so this is imperative state
        # that nix only bootstraps.
        run mkdir -p "$fnm_dir/aliases"
        run ${pkgs.fnm}/bin/fnm --fnm-dir "$fnm_dir" install --lts --corepack-enabled >/dev/null 2>&1 \
          && run ${pkgs.fnm}/bin/fnm --fnm-dir "$fnm_dir" default lts-latest >/dev/null 2>&1 \
          || true
      fi
    '';
  };
}
