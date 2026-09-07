{
  pkgs,
  lib,
  ...
}: {
  nixos = {
    boot.binfmt.emulatedSystems = ["aarch64-linux"];

    virtualisation.docker.enable = true;
    users.users.potb.extraGroups = lib.mkAfter ["docker"];
  };

  darwin = {};

  home = {
    home.packages = with pkgs;
      [
        docker-client
        docker-buildx
        docker-compose
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isDarwin [
        colima
        lima
      ];

    # macOS has no native container runtime, so Docker runs against a Linux VM.
    # Declaring the profile keeps `colima start` reproducible: without it the
    # first start bakes colima's own defaults (2 CPUs, 2GiB) into a persisted
    # profile that later edits of this file would not reach.
    home.file.".colima/default/colima.yaml" = lib.mkIf pkgs.stdenv.hostPlatform.isDarwin {
      text = ''
        cpu: 4
        memory: 8
        disk: 60
        runtime: docker
        arch: aarch64
        vmType: vz
        rosetta: true
        mountType: virtiofs
        mounts:
          - location: ~
            writable: true
        autoActivate: true
        network:
          address: false
          dns: []
          dnsHosts: {}
      '';
    };
  };
}
