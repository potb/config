{
  pkgs,
  lib,
  ...
}: let
  # In preference order. The first candidate that is online, offers itself as an
  # exit node, and actually carries traffic wins.
  candidates = ["charon" "kerberos"];

  # Proves egress rather than trusting the control plane: a peer can report
  # itself online and still fail to route.
  probeUrl = "https://api.ipify.org";
  probeTimeout = 8;

  pick = pkgs.writeShellApplication {
    name = "tailscale-exit-node-pick";
    runtimeInputs = with pkgs; [tailscale jq curl];
    text = ''
      candidates=(${lib.concatStringsSep " " (map lib.escapeShellArg candidates)})

      if ! status=$(tailscale status --json 2>/dev/null); then
        echo "tailscaled is not answering, leaving the exit node alone"
        exit 0
      fi

      # A tailnet of one has no .Peer at all.
      backend=$(jq -r '.BackendState // ""' <<<"$status")
      if [ "$backend" != "Running" ]; then
        echo "tailscale is $backend, leaving the exit node alone"
        exit 0
      fi

      current_host=$(jq -r '
        (.ExitNodeStatus.ID // "") as $id
        | if $id == "" then ""
          else ([(.Peer // {})[] | select(.ID == $id) | .HostName] | first // "")
          end
      ' <<<"$status")

      eligible() {
        jq -e --arg host "$1" '
          [(.Peer // {})[]
           | select((.HostName // "") == $host)
           | select(.Online == true)
           | select(.ExitNodeOption == true)]
          | length > 0
        ' <<<"$status" >/dev/null
      }

      egress_works() {
        curl --silent --show-error --fail \
          --max-time ${toString probeTimeout} \
          --output /dev/null \
          ${lib.escapeShellArg probeUrl}
      }

      # Nothing to do while the current choice is still the best one and works.
      if [ -n "$current_host" ] && [ "$current_host" = "''${candidates[0]}" ] \
        && eligible "$current_host" && egress_works; then
        exit 0
      fi

      for candidate in "''${candidates[@]}"; do
        if ! eligible "$candidate"; then
          continue
        fi

        if [ "$candidate" != "$current_host" ]; then
          echo "selecting exit node $candidate"
          # Fails when the route lost its approval between the status read and
          # here, which is a reason to try the next candidate, not to give up.
          if ! tailscale set --exit-node="$candidate"; then
            echo "$candidate refused the selection"
            continue
          fi
          # `set` returns before the route is in place.
          sleep 2
        fi

        if egress_works; then
          echo "egress through $candidate is working"
          exit 0
        fi

        echo "$candidate advertises an exit node but does not carry traffic"
      done

      # Fail open. Tailscale would otherwise keep a dead default route and take
      # the host off the internet with it.
      if [ -n "$current_host" ]; then
        echo "no exit node available, clearing $current_host"
        tailscale set --exit-node=
      fi
    '';
  };
in {
  nixos = {
    services.tailscale = {
      useRoutingFeatures = "client";

      # Without this the exit node route claims the local subnets too, podman's
      # 10.88.0.0/16 among them, and every container loses the internet the
      # moment an exit node is selected. It turns those routes into `throw`,
      # which sends them back to the main table.
      extraSetFlags = ["--exit-node-allow-lan-access"];
    };

    systemd.services.tailscale-exit-node = {
      description = "Select a working tailnet exit node, or none";
      after = [
        "tailscaled.service"
        "tailscaled-autoconnect.service"
        # Never select an exit node before the rule that keeps replies to
        # inbound traffic off it, or the window between the two takes public
        # SSH down on a host whose other way in is a VNC console.
        "exit-node-bypass-rule.service"
      ];
      wants = ["tailscaled.service"];
      requires = ["exit-node-bypass-rule.service"];

      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.getExe pick;
      };
    };

    systemd.timers.tailscale-exit-node = {
      description = "Re-check the tailnet exit node";
      wantedBy = ["timers.target"];

      timerConfig = {
        OnBootSec = "30s";
        OnUnitInactiveSec = "30s";
        AccuracySec = "5s";
        Unit = "tailscale-exit-node.service";
      };
    };
  };

  darwin = {};
  home = {};
}
