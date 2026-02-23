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
        docker-compose
      ]
      ++ lib.optionals pkgs.stdenv.isDarwin [
        colima
        lima
      ];
  };
}
