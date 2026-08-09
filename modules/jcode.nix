{...}: {
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
  home = {config, ...}: {
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

        # 1 means the daemon refused to start, and every such refusal is
        # permanent: overwhelmingly it is losing the flock on
        # $XDG_RUNTIME_DIR/jcode-daemon.lock to a daemon already serving this
        # runtime dir (a terminal-launched one, or a client that spawned its
        # own). Retrying cannot win a lock the incumbent holds for its whole
        # lifetime, and StartLimitBurst does not catch it: a failed start takes
        # about a second and RestartSec adds two, so only ~3 attempts fall in
        # the default 10s window and the unit restarts forever without ever
        # tripping the limiter. Verified: without this the unit logged
        # NRestarts=11 in 25s and climbing; with it, one clean failure.
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
