{
  pkgs,
  lib,
  ...
}: let
  optionsModule = {lib, ...}: {
    options.services.screenpipe-export = {
      enable = lib.mkEnableOption "export screenpipe captures into Honcho";
      workspace = lib.mkOption {
        type = lib.types.str;
        default = "rakazo-79c4ac8418b2f8c178d31b226cdd342f";
      };
      hours = lib.mkOption {
        type = lib.types.int;
        default = 2;
      };
      secretPath = lib.mkOption {
        type = lib.types.str;
        default = ".config/honcho/api-key";
      };
      meetings = lib.mkOption {
        type = lib.types.bool;
        default = true;
      };
      meetingNotesState = lib.mkOption {
        type = lib.types.str;
        default = ".local/share/meeting-notes/state.json";
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
    cfg = osConfig.services.screenpipe-export;
    homeDir = config.home.homeDirectory;
    keyPath = "${homeDir}/${cfg.secretPath}";
    environment = {
      HONCHO_WORKSPACE = cfg.workspace;
      EXPORT_HOURS = toString cfg.hours;
      HONCHO_API_KEY_FILE = keyPath;
      EXPORT_STATE = "${homeDir}/.local/state/screenpipe-export/cursor";
      EXPORT_MEETINGS =
        if cfg.meetings
        then "1"
        else "0";
      EXPORT_MEETINGS_STATE = "${homeDir}/.local/state/screenpipe-export/meetings.json";
      MEETING_NOTES_STATE = "${homeDir}/${cfg.meetingNotesState}";
      SCREENPIPE_BIN = lib.getExe' pkgs.screenpipe "screenpipe";
    };
  in {
    linux = lib.mkIf cfg.enable {
      sops.secrets.honcho-api-key = {
        sopsFile = ../../secrets/honcho.yaml;
        key = "honcho-api-key";
        path = keyPath;
      };

      systemd.user.services.screenpipe-export = {
        Unit = {
          Description = "Export screenpipe captures into Honcho";
          After = ["default.target"];
        };
        Service = {
          Type = "oneshot";
          ExecStart = "${pkgs.python3}/bin/python3 ${./screenpipe-export/export.py}";
          Environment = lib.mapAttrsToList (name: value: "${name}=${value}") environment;
        };
      };

      systemd.user.timers.screenpipe-export = {
        Unit.Description = "Hourly screenpipe export into Honcho";
        Timer = {
          OnCalendar = "hourly";
          Persistent = true;
          RandomizedDelaySec = "5m";
        };
        Install.WantedBy = ["timers.target"];
      };
    };
  };
}
