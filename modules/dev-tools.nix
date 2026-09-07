{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};
  home = {
    config,
    lib,
    ...
  }: {
    home.packages = with pkgs; [
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

      awscli2
      stripe-cli

      rtk
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
