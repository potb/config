{
  pkgs,
  lib,
  ...
}: let
  optionsModule = {
    lib,
    pkgs,
    ...
  }: {
    options.services.meeting-notes = {
      diarization = {
        enable = lib.mkOption {
          type = lib.types.bool;
          default = pkgs.stdenv.hostPlatform.isLinux;
        };
        threads = lib.mkOption {
          type = lib.types.ints.positive;
          default = 4;
        };
        maxDelayMinutes = lib.mkOption {
          type = lib.types.ints.unsigned;
          default = 180;
        };
      };
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
      notesModel = lib.mkOption {
        type = lib.types.str;
        default = "sonnet";
      };
      ocrLanguages = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = ["eng" "fra"];
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
      ignoreApps = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [];
      };
      slack = {
        enable = lib.mkOption {
          type = lib.types.bool;
          default = false;
        };
        postTo = lib.mkOption {
          type = lib.types.enum ["dm" "channel"];
          default = "dm";
        };
        channelId = lib.mkOption {
          type = lib.types.str;
          default = "";
        };
        userId = lib.mkOption {
          type = lib.types.str;
          default = "";
        };
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
    slackSecret = ../../secrets/meeting-notes.yaml;
    slackSops = pkgs.stdenv.hostPlatform.isLinux && cfg.slack.enable && builtins.pathExists slackSecret;
    slackTokenPath = "${homeDir}/.config/meeting-notes/slack-bot-token";
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
        MEETING_NOTES_DIARIZATION = flag cfg.diarization.enable;
        MEETING_NOTES_DIARIZATION_THREADS = toString cfg.diarization.threads;
        MEETING_NOTES_DIARIZATION_MAX_DELAY = toString cfg.diarization.maxDelayMinutes;
        MEETING_NOTES_FFMPEG = lib.getExe pkgs.ffmpeg;
        MEETING_NOTES_CLAUDE = "${profileBin}/claude";
        MEETING_NOTES_CLAUDE_MODEL = cfg.notesModel;
        MEETING_NOTES_TESSERACT = lib.getExe (pkgs.tesseract5.override {enableLanguages = cfg.ocrLanguages;});
        MEETING_NOTES_OCR_LANGUAGES = lib.concatStringsSep "+" cfg.ocrLanguages;
        MEETING_NOTES_RETENTION_DAYS = toString cfg.retentionDays;
        MEETING_NOTES_MIN_MINUTES = toString cfg.minMinutes;
        MEETING_NOTES_IGNORE_APPS = lib.concatStringsSep "," cfg.ignoreApps;
        MEETING_NOTES_SLACK = flag cfg.slack.enable;
        MEETING_NOTES_SLACK_POST_TO = cfg.slack.postTo;
        MEETING_NOTES_SLACK_CHANNEL = cfg.slack.channelId;
        MEETING_NOTES_SLACK_USER = cfg.slack.userId;
        MEETING_NOTES_SCREENPIPE_URL = "http://127.0.0.1:3030";
        MEETING_NOTES_AUDIO_DIR =
          if cfg.backend == "native"
          then "${dataDir}/audio"
          else "${homeDir}/.screenpipe/data";
      }
      // lib.optionalAttrs cfg.diarization.enable {
        MEETING_NOTES_SPEAKER_MODEL = "${pkgs.meeting-notes-models.wespeaker-resnet34}";
        MEETING_NOTES_DIARIZATION_VAD_MODEL = "${pkgs.meeting-notes-models.silero-vad-onnx}";
      }
      // lib.optionalAttrs slackSops {
        MEETING_NOTES_SLACK_TOKEN_FILE = slackTokenPath;
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

    linux.sops.secrets = lib.mkIf slackSops {
      meeting-notes-slack-bot-token = {
        sopsFile = slackSecret;
        key = "slack-bot-token";
        path = slackTokenPath;
      };
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
