{pkgs, ...}: {
  home-manager.users.potb = {
    home.packages = [pkgs.screenpipe];

    systemd.user.services.screenpipe = {
      Unit = {
        Description = "screenpipe screen and audio recorder";
        PartOf = ["graphical-session.target"];
        After = ["graphical-session.target" "pipewire-pulse.service"];
      };
      Service = {
        ExecStart = "${pkgs.screenpipe}/bin/screenpipe record --port 3030 --disable-telemetry";
        Environment = ["SCREENPIPE_WAYLAND_CAPTURE=grim"];
        Restart = "always";
        RestartSec = 10;
      };
      Install.WantedBy = ["graphical-session.target"];
    };
  };
}
