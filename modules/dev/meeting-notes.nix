{
  pkgs,
  lib,
  ...
}: let
  optionsModule = {lib, ...}: {
    options.services.meeting-notes = {
      owner = lib.mkOption {
        type = lib.types.str;
        default = "Peïo";
      };
      backend = lib.mkOption {
        type = lib.types.enum ["native" "screenpipe"];
        default = "native";
      };
      model = lib.mkOption {
        type = lib.types.enum ["large-v3" "large-v3-turbo"];
        default = "large-v3";
      };
      live = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };
      language = lib.mkOption {
        type = lib.types.str;
        default = "fr";
      };
      retentionDays = lib.mkOption {
        type = lib.types.int;
        default = 7;
      };
      minMinutes = lib.mkOption {
        type = lib.types.int;
        default = 5;
      };
      slack.enable = lib.mkOption {
        type = lib.types.bool;
        default = false;
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
    cfg = osConfig.services.meeting-notes;
    homeDir = config.home.homeDirectory;
    dataDir = "${homeDir}/.local/share/meeting-notes";
    profileBin = "/etc/profiles/per-user/${config.home.username}/bin";
    flag = value:
      if value
      then "1"
      else "0";
    whisper =
      if pkgs.stdenv.hostPlatform.isLinux
      then "${pkgs.whisper-cpp-vulkan}/bin/whisper-cli"
      else "${pkgs.whisper-cpp}/bin/whisper-cli";
    meetingNotes = lib.getExe' pkgs.meeting-notes "meeting-notes";
    environment =
      {
        MEETING_NOTES_DATA_DIR = dataDir;
        MEETING_NOTES_MEETINGS_DIR = "${homeDir}/Meetings";
        MEETING_NOTES_BACKEND = cfg.backend;
        MEETING_NOTES_LIVE = flag cfg.live;
        MEETING_NOTES_LANGUAGE = cfg.language;
        MEETING_NOTES_OWNER = cfg.owner;
        MEETING_NOTES_WHISPER = whisper;
        MEETING_NOTES_MODEL = "${pkgs.meeting-notes-models.${cfg.model}}";
        MEETING_NOTES_VAD_MODEL = "${pkgs.meeting-notes-models.silero-vad}";
        MEETING_NOTES_FFMPEG = lib.getExe pkgs.ffmpeg;
        MEETING_NOTES_CLAUDE = "${profileBin}/claude";
        MEETING_NOTES_RETENTION_DAYS = toString cfg.retentionDays;
        MEETING_NOTES_MIN_MINUTES = toString cfg.minMinutes;
        MEETING_NOTES_SLACK = flag cfg.slack.enable;
        MEETING_NOTES_SCREENPIPE_URL = "http://127.0.0.1:3030";
        MEETING_NOTES_AUDIO_DIR =
          if cfg.backend == "native"
          then "${dataDir}/audio"
          else "${homeDir}/.screenpipe/data";
      }
      // lib.optionalAttrs (cfg.backend == "screenpipe") {
        MEETING_NOTES_SCREENPIPE = lib.getExe' pkgs.screenpipe "screenpipe";
      };
    servicePath = lib.concatStringsSep ":" (
      [profileBin]
      ++ map (p: "${lib.getBin p}/bin") [
        pkgs.pipewire
        pkgs.pulseaudio
        pkgs.hyprland
        pkgs.grim
        pkgs.libnotify
        pkgs.util-linux
        pkgs.coreutils
        pkgs.ffmpeg
      ]
    );
    shared = name: "${pkgs.meeting-notes}/share/meeting-notes/${name}";
  in {
    home.packages = [pkgs.meeting-notes];

    home.file = {
      ".local/share/meeting-notes/pipe.md".source = shared "pipe.md";
      ".local/share/meeting-notes/glossary.md".source = shared "glossary.md";
    };

    linux.systemd.user.services.meeting-notes = {
      Unit = {
        Description = "Detect meetings and turn them into notes";
        After = ["graphical-session.target" "pipewire-pulse.service"];
        PartOf = ["graphical-session.target"];
      };
      Service = {
        ExecStart = "${meetingNotes} watch";
        Environment =
          lib.mapAttrsToList (name: value: "${name}=${value}") environment
          ++ ["PATH=${servicePath}"];
        Restart = "always";
        RestartSec = 10;
      };
      Install.WantedBy = ["graphical-session.target"];
    };

    darwin.launchd.agents =
      {
        meeting-notes = {
          enable = true;
          config = {
            ProgramArguments = [meetingNotes "watch"];
            EnvironmentVariables =
              environment
              // {
                PATH = "${profileBin}:/usr/bin:/bin:/usr/sbin:/sbin";
              };
            KeepAlive = true;
            RunAtLoad = true;
            StandardOutPath = "${dataDir}/watch.log";
            StandardErrorPath = "${dataDir}/watch.log";
          };
        };
      }
      // lib.optionalAttrs (cfg.backend == "screenpipe") {
        screenpipe = {
          enable = true;
          config = {
            ProgramArguments = [meetingNotes "screenpipe"];
            EnvironmentVariables =
              environment
              // {
                PATH = "${profileBin}:/usr/bin:/bin:/usr/sbin:/sbin";
              };
            KeepAlive = true;
            RunAtLoad = true;
            StandardOutPath = "${dataDir}/screenpipe.log";
            StandardErrorPath = "${dataDir}/screenpipe.log";
          };
        };
      };
  };
}
