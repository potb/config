{
  pkgs,
  lib,
  ...
}: let
  bake = name: profile:
    pkgs.gogcli.overrideAttrs (old: {
      pname = "gogcli-${name}";
      tags = (old.tags or []) ++ ["safety_profile"];
      postConfigure =
        (old.postConfigure or "")
        + ''
          go run ./cmd/bake-safety-profile ${profile} internal/cmd/safety_profile_baked_gen.go
        '';
      doCheck = false;
    });

  gogHal = (bake "hal" ./gog-hal.yaml).overrideAttrs (old: {
    patches = (old.patches or []) ++ [./gog-private-calendar.patch];
  });

  gogMailReader = bake "mail-reader" ./gog-mail-reader.yaml;

  tesseract = pkgs.tesseract.override {
    enableLanguages = [
      "fra"
      "eng"
    ];
  };

  mailScript = pkgs.writeScript "mail.py" (
    "#!${lib.getExe pkgs.python3}\n" + builtins.readFile ./mail.py
  );

  mail = pkgs.writeShellScriptBin "mail" ''
    export MAIL_GOG=${gogMailReader}/bin/gog
    export PATH=${lib.makeBinPath [pkgs.poppler-utils tesseract]}:$PATH
    exec ${mailScript} "$@"
  '';
in {
  nixos = {
    services.openclaw-gateway.servicePath = [
      gogHal
      mail
    ];

    systemd.tmpfiles.rules = [
      "d /var/lib/openclaw/workspace/mail 0750 openclaw openclaw - -"
    ];
  };

  darwin = {};
  home = {};
}
