{
  config,
  pkgs,
  ...
}: let
  keys = import ../../../shared/keys.nix;

  stateDir = "/var/lib/nixos-deploy";
  requestDir = "${stateDir}/requests";
  deployedMarker = "${stateDir}/deployed";
  repository = "potb/config";
  installable = "${stateDir}/repo#nixosConfigurations.new-horizons.config.system.build.toplevel";

  queueRequest = pkgs.writeShellApplication {
    name = "nixos-deploy-request";
    runtimeInputs = [pkgs.coreutils];
    text = ''
      sha=''${SSH_ORIGINAL_COMMAND:-}
      if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then
        echo "expected a commit sha, got: $sha" >&2
        exit 2
      fi
      touch "${requestDir}/$sha"
      echo "new-horizons queued a deploy for $sha"
    '';
  };

  deployMaster = pkgs.writeShellApplication {
    name = "nixos-deploy";
    runtimeInputs = [
      config.nix.package
      config.systemd.package
      pkgs.coreutils
      pkgs.gh
      pkgs.git
      pkgs.gnugrep
      pkgs.jq
    ];
    text = ''
      repo=${stateDir}/repo
      token=${config.sops.secrets.github-deploy-token.path}

      clear_pending_requests() {
        rm -f "${requestDir}"/*
      }

      running_system() {
        readlink -f /run/current-system
      }

      is_already_deployed() {
        [ "$sha $(running_system)" = "$(cat ${deployedMarker} 2>/dev/null || true)" ]
      }

      mark_deployed() {
        echo "$sha $1" >${deployedMarker}
      }

      public_log_tail() {
        tail -n 150 "$1" | tail -c 20000
      }

      failed_units_line() {
        grep -o 'the following units failed: .*' "$1" | head -n 1 || true
      }

      report_to_github() {
        local state=$1 description=$2 log_tail=$3
        echo "$state: $description"
        if [ ! -s "$token" ]; then
          return 0
        fi
        jq -n --arg sha "$sha" --arg state "$state" \
          --arg description "$description" --arg log "$log_tail" \
          '{sha: $sha, state: $state, description: $description, log: $log}' \
          | GH_TOKEN=$(cat "$token") \
            gh workflow run deploy-report.yml --repo ${repository} --ref master --json \
          || echo "could not report $state to GitHub" >&2
      }

      clear_pending_requests

      if [ ! -d "$repo/.git" ]; then
        git clone --quiet https://github.com/${repository} "$repo"
      fi
      git -C "$repo" fetch --quiet origin master
      sha=$(git -C "$repo" rev-parse FETCH_HEAD)

      if is_already_deployed; then
        echo "$sha is already deployed"
        exit 0
      fi

      git -C "$repo" checkout --quiet --force --detach "$sha"
      git -C "$repo" clean --quiet -ffdx

      log=$(mktemp)
      trap 'rm -f "$log"' EXIT

      if ! paths=$(nix eval --json "${installable}" \
        --apply 't: { drv = t.drvPath; out = t.outPath; }' 2>"$log"); then
        cat "$log" >&2
        report_to_github failure "evaluation failed" "$(public_log_tail "$log")"
        exit 1
      fi
      drv=$(jq -r .drv <<<"$paths")
      wanted=$(jq -r .out <<<"$paths")

      if [ "$wanted" = "$(running_system)" ]; then
        mark_deployed "$wanted"
        report_to_github success "no change for new-horizons" ""
        exit 0
      fi

      report_to_github pending "building ''${wanted#/nix/store/}" ""
      if ! nix build --no-link --print-build-logs "$drv^*" >"$log" 2>&1; then
        cat "$log" >&2
        report_to_github failure "build failed" "$(public_log_tail "$log")"
        exit 1
      fi

      nix-env --profile /nix/var/nix/profiles/system --set "$wanted"
      if ! systemd-run --collect --no-ask-password --pipe --quiet \
        --service-type=exec --unit=nixos-deploy-switch \
        "$wanted/bin/switch-to-configuration" switch >"$log" 2>&1; then
        cat "$log" >&2
        failed_units=$(failed_units_line "$log")
        report_to_github failure "switch failed''${failed_units:+, $failed_units}" ""
        exit 1
      fi
      cat "$log"

      mark_deployed "$wanted"
      report_to_github success "switched to ''${wanted#/nix/store/}" ""
    '';
  };

  lowPriority = {
    Nice = 19;
    CPUWeight = 20;
    IOSchedulingClass = "idle";
    IOWeight = 20;
    OOMScoreAdjust = 500;
  };

  surviveOwnSwitch = {
    restartIfChanged = false;
    stopIfChanged = false;
  };
in {
  sops.secrets.github-deploy-token = {
    sopsFile = ../../../secrets/new-horizons.yaml;
  };

  users.users.deploy = {
    isSystemUser = true;
    group = "deploy";
    shell = pkgs.bash;
    openssh.authorizedKeys.keys = [
      ''restrict,command="${queueRequest}/bin/nixos-deploy-request" ${keys.github-actions}''
    ];
  };
  users.groups.deploy = {};

  services.openssh.settings.AllowUsers = ["deploy"];

  systemd.tmpfiles.rules = [
    "d ${stateDir} 0755 root root -"
    "d ${requestDir} 0700 deploy deploy -"
  ];

  systemd.paths.nixos-deploy = {
    description = "Watch for deploy requests from GitHub Actions";
    wantedBy = ["paths.target"];
    pathConfig.DirectoryNotEmpty = requestDir;
  };

  systemd.services.nixos-deploy =
    surviveOwnSwitch
    // {
      description = "Build master on this host and switch to it";
      after = ["network-online.target"];
      wants = ["network-online.target"];
      environment.HOME = "/root";

      serviceConfig =
        lowPriority
        // {
          Type = "oneshot";
          ExecStart = "${deployMaster}/bin/nixos-deploy";
          TimeoutStartSec = "3h";
        };
    };
}
