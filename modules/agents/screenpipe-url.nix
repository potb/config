{
  pkgs,
  lib,
  ...
}: let
  optionsModule = {lib, ...}: {
    options.services.screenpipe-url = {
      enable = lib.mkEnableOption "record the URL of the focused Chrome window through AT-SPI";
      statePath = lib.mkOption {
        type = lib.types.str;
        default = ".local/state/screenpipe-url/urls.jsonl";
      };
      interval = lib.mkOption {
        type = lib.types.numbers.positive;
        default = 2.5;
      };
      maxMegabytes = lib.mkOption {
        type = lib.types.numbers.positive;
        default = 10;
      };
    };
  };
in {
  nixos.imports = [optionsModule];
  darwin.imports = [optionsModule];

  home = {
    config,
    osConfig,
    ...
  }: let
    cfg = osConfig.services.screenpipe-url;
    environment = {
      SCREENPIPE_URL_STATE = "${config.home.homeDirectory}/${cfg.statePath}";
      SCREENPIPE_URL_INTERVAL = toString cfg.interval;
      SCREENPIPE_URL_MAX_MB = toString cfg.maxMegabytes;
    };
  in {
    linux = lib.mkIf cfg.enable {
      home.packages = [pkgs.screenpipe-url];

      systemd.user.services.screenpipe-url = {
        Unit = {
          Description = "Record the URL of the focused Chrome window";
          PartOf = ["graphical-session.target"];
          After = ["graphical-session.target"];
        };
        Service = {
          ExecStart = lib.getExe pkgs.screenpipe-url;
          Environment = lib.mapAttrsToList (name: value: "${name}=${value}") environment;
          Restart = "always";
          RestartSec = 10;
        };
        Install.WantedBy = ["graphical-session.target"];
      };
    };
  };
}
