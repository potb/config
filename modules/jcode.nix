{...}: {
  nixos = {};
  darwin = {};

  # Supervise the jcode daemon so the ambient loop and its scheduled jobs run
  # in the background, instead of only while a terminal happens to be open.
  home = {config, ...}: {
    systemd.user.services.jcode = {
      Unit = {
        Description = "jcode shared daemon (sessions, ambient loop, scheduled jobs)";
        After = ["network-online.target" "dbus.service"];
        Wants = ["network-online.target"];
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
    # their environment from environment.d, which does expand $PATH.
    systemd.user.sessionVariables.PATH = "$HOME/.local/bin:$HOME/.cargo/bin:$PATH";
  };
}
