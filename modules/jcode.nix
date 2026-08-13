{
  inputs,
  lib,
  ...
}: {
  # Linger, so the user manager (and with it the daemon) starts at boot and
  # survives logout. Without it a "background" daemon is only alive between
  # login and logout, which is the exact window the schedules are meant to
  # outlast.
  nixos = {
    users.users.potb.linger = true;
  };

  darwin = {};

  # Supervise the jcode daemon so the ambient loop and its scheduled jobs run
  # in the background, instead of only while a terminal happens to be open.
  home = {
    config,
    lib,
    pkgs,
    ...
  }: let
    # Seeded, not managed: home.file would install read-only store symlinks, and
    # these files are edited live. Copy an edit back into this repo to persist it.
    seedFiles = {
      ".jcode/prompt-overlay.md" = ./jcode/prompt-overlay.md;
      ".jcode/skills/garden-memory/SKILL.md" = ./jcode/garden-memory-SKILL.md;
    };

    seedScript = lib.concatStringsSep "\n" (lib.mapAttrsToList (rel: src: ''
        seed_jcode_file ${lib.escapeShellArg rel} ${lib.escapeShellArg "${src}"}
      '')
      seedFiles);
  in {
    # Overwrites only while the target still matches what was seeded last time.
    # Once edited, the live file wins and the nix version lands in <file>.nix-new.
    home.activation.seedJcodeFiles = lib.hm.dag.entryAfter ["writeBoundary"] ''
      seed_jcode_file() {
        dest="$HOME/$1"
        src="$2"
        stamp="$(dirname "$dest")/.$(basename "$dest").nix-seeded"

        $DRY_RUN_CMD mkdir -p "$(dirname "$dest")"

        # -L catches a store symlink left by an earlier home.file generation.
        if [ ! -e "$dest" ] || [ -L "$dest" ] \
          || ${pkgs.diffutils}/bin/cmp -s "$dest" "$stamp"; then
          $DRY_RUN_CMD rm -f "$dest"
          $DRY_RUN_CMD install -m 0644 "$src" "$dest"
          $DRY_RUN_CMD install -m 0644 "$src" "$stamp"
        elif ${pkgs.diffutils}/bin/cmp -s "$dest" "$src"; then
          $DRY_RUN_CMD install -m 0644 "$src" "$stamp"
        else
          $DRY_RUN_CMD install -m 0644 "$src" "$dest.nix-new"
          echo "jcode: kept live edits in $dest (nix version at $dest.nix-new)"
        fi
      }

      ${seedScript}
    '';

    systemd.user.services.jcode = {
      Unit = {
        Description = "jcode shared daemon (sessions, ambient loop, scheduled jobs)";

        # No network ordering, deliberately. network-online.target is a system
        # unit, and a user unit cannot order against one, which is why the
        # usual Wants=/After= pair silently resolves to nothing here. It would
        # buy nothing anyway: the daemon boots and binds its socket with no
        # network at all (verified under `unshare -n`), and every call it makes
        # afterwards already goes through its own reconnect-and-retry path.
        #
        # graphical-session.target is likewise avoided, so the daemon survives
        # logging out of Hyprland rather than being torn down with the session.
        After = ["dbus.service"];
      };

      Service = {
        Type = "simple";

        # The launcher symlink, not a store path: self-dev and release installs
        # repoint ~/.jcode/builds/current and the unit should follow them.
        ExecStart = "${config.home.homeDirectory}/.local/bin/jcode serve";

        # on-failure, not always: `jcode server stop` SIGTERMs the daemon and
        # expects it to stay down.
        Restart = "on-failure";
        RestartSec = 2;

        # 42 = reload exec failed, so no replacement was started.
        # 44 = idle timeout; a supervised daemon should wait for the next client.
        RestartForceExitStatus = "42 44";

        # 1 means the daemon refused to start, and the refusals are permanent:
        # losing the flock on $XDG_RUNTIME_DIR/jcode-daemon.lock to a daemon
        # already serving this runtime dir (the usual case, from a
        # terminal-launched one or a client that spawned its own), or an
        # unusable socket path. Retrying cannot win a lock the incumbent holds
        # for its whole lifetime, and StartLimitBurst does not catch it: a
        # failed start takes about a second and RestartSec adds two, so only ~3
        # attempts fall in the default 10s window and the unit restarts forever
        # without ever tripping the limiter. Verified: without this the unit
        # logged NRestarts=11 in 25s and climbing; with it, one clean failure.
        #
        # The plausible transient causes were checked and do not exit 1. With
        # no network at all (`unshare -rn`, the boot-time worry) the daemon
        # boots and keeps serving, and with no credentials at all it also stays
        # up rather than bailing, so a slow-starting network or a not-yet-ready
        # secret cannot wedge the unit here.
        RestartPreventExitStatus = "1";

        # JCODE_DEBUG_CONTROL disables the daemon's idle exit. Everything else
        # it shells out to (git, gh, notify-send) is already on the systemd
        # user manager's PATH; see systemd.user.sessionVariables below for the
        # two user bin dirs that are not.
        Environment = ["JCODE_DEBUG_CONTROL=1"];

        # Signal the daemon only; its children are the in-flight turn's
        # subprocesses, which it winds down itself.
        KillMode = "mixed";
        KillSignal = "SIGTERM";
        TimeoutStopSec = 30;
      };

      Install.WantedBy = ["default.target"];
    };

    # home.sessionPath only reaches shells, via hm-session-vars.sh. Units get
    # their environment from environment.d, whose files are merged in
    # lexicographic order by filename across every search directory.
    #
    # systemd.user.sessionVariables cannot be used for PATH here: it writes
    # 10-home-manager.conf, and NixOS ships /etc/environment.d/50-systemd-path.conf
    # which assigns PATH outright rather than extending it, so the higher number
    # wins and the home-manager value is silently discarded. Verified by running
    # the real 30-systemd-environment-d-generator: with the 10- prefix neither
    # directory appears in the result, with a 90- prefix both do.
    #
    # jcode itself is started by absolute path, so this is for what it shells
    # out to: agent commands and scheduled jobs that invoke `jcode`, plus
    # cargo-installed tools. git, gh and notify-send already resolve via
    # /etc/profiles/per-user/potb/bin.
    xdg.configFile."environment.d/90-user-path.conf".text = ''
      PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
    '';
  };
}
