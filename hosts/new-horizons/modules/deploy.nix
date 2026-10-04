{
  config,
  pkgs,
  ...
}: let
  keys = import ../../../shared/keys.nix;

  stateDir = "/var/lib/nixos-deploy";
  requestDir = "${stateDir}/requests";
  repository = "potb/config";
  installable = "${stateDir}/repo#nixosConfigurations.new-horizons.config.system.build.toplevel";

  # The only thing the GitHub Actions key can run. It leaves a request behind
  # and returns, so the job on GitHub finishes in seconds whatever the build
  # costs, and a leaked key can ask for nothing but a deploy of master.
  request = pkgs.writeShellApplication {
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

  deploy = pkgs.writeShellApplication {
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
      # Taken first, so a push that lands mid-build leaves a new request behind
      # and the path unit starts another run as soon as this one ends.
      rm -f "${requestDir}"/*

      repo=${stateDir}/repo
      if [ ! -d "$repo/.git" ]; then
        git clone --quiet https://github.com/${repository} "$repo"
      fi
      git -C "$repo" fetch --quiet origin master
      sha=$(git -C "$repo" rev-parse FETCH_HEAD)

      # A second request for the same commit, unless the running system has
      # since been switched by hand, as a deploy from charon does.
      if [ "$sha $(readlink -f /run/current-system)" = "$(cat ${stateDir}/deployed 2>/dev/null || true)" ]; then
        echo "$sha is already deployed"
        exit 0
      fi

      git -C "$repo" checkout --quiet --force --detach "$sha"
      git -C "$repo" clean --quiet -ffdx

      token=${config.sops.secrets.github-deploy-token.path}
      log=$(mktemp)
      trap 'rm -f "$log"' EXIT

      # Lands on GitHub as a workflow run, which sets the commit status and
      # fails when the deploy did, so a failure reaches the notifications of
      # whoever owns the token. Reporting is best effort: a broken token must
      # not stop a deploy.
      report() {
        local state=$1 description=$2 tail=""
        if [ -n "''${3:-}" ]; then
          tail=$(tail -n 150 "$3" | tail -c 20000)
        fi
        echo "$state: $description"
        if [ ! -s "$token" ]; then
          return 0
        fi
        jq -n --arg sha "$sha" --arg state "$state" \
          --arg description "$description" --arg log "$tail" \
          '{sha: $sha, state: $state, description: $description, log: $log}' \
          | GH_TOKEN=$(cat "$token") \
            gh workflow run deploy-report.yml --repo ${repository} --ref master --json \
          || echo "could not report $state to GitHub" >&2
      }

      if ! paths=$(nix eval --json "${installable}" \
        --apply 't: { drv = t.drvPath; out = t.outPath; }' 2>"$log"); then
        cat "$log" >&2
        report failure "evaluation failed" "$log"
        exit 1
      fi
      drv=$(jq -r .drv <<<"$paths")
      wanted=$(jq -r .out <<<"$paths")

      # Most pushes touch other hosts or only docs. Their system is the one
      # already running, so there is nothing to build.
      if [ "$wanted" = "$(readlink -f /run/current-system)" ]; then
        echo "$sha $wanted" >${stateDir}/deployed
        report success "no change for new-horizons"
        exit 0
      fi

      report pending "building ''${wanted#/nix/store/}"
      if ! nix build --no-link --print-build-logs "$drv^*" >"$log" 2>&1; then
        cat "$log" >&2
        report failure "build failed" "$log"
        exit 1
      fi

      # Activation output can quote the journal of a failing unit, which may
      # hold the agent's conversations, and the report is public. Only the
      # names of failed units leave the host.
      nix-env --profile /nix/var/nix/profiles/system --set "$wanted"
      if ! systemd-run --collect --no-ask-password --pipe --quiet \
        --service-type=exec --unit=nixos-deploy-switch \
        "$wanted/bin/switch-to-configuration" switch >"$log" 2>&1; then
        cat "$log" >&2
        failed=$(grep -o 'the following units failed: .*' "$log" | head -n 1 || true)
        report failure "switch failed''${failed:+, $failed}"
        exit 1
      fi
      cat "$log"

      echo "$sha $wanted" >${stateDir}/deployed
      report success "switched to ''${wanted#/nix/store/}"
    '';
  };
in {
  sops.secrets.github-deploy-token = {
    sopsFile = ../../../secrets/new-horizons.yaml;
  };

  users.users.deploy = {
    isSystemUser = true;
    group = "deploy";
    # sshd hands the forced command to the login shell, so nologin would
    # refuse it. `restrict` still forbids a pty, forwarding and anything else.
    shell = pkgs.bash;
    openssh.authorizedKeys.keys = [
      ''restrict,command="${request}/bin/nixos-deploy-request" ${keys.github-actions}''
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

  systemd.services.nixos-deploy = {
    description = "Build master on this host and switch to it";
    after = ["network-online.target"];
    wants = ["network-online.target"];

    # The switch this unit performs may change the unit itself. Restarting it
    # then would kill the deploy halfway. The switch runs in its own transient
    # unit for the same reason.
    restartIfChanged = false;
    stopIfChanged = false;

    environment.HOME = "/root";

    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${deploy}/bin/nixos-deploy";
      TimeoutStartSec = "3h";

      # This host runs the agent on 4 vCPUs and 7 GB. Builds take what the
      # agent leaves, and the kernel kills a build before the agent.
      Nice = 19;
      CPUWeight = 20;
      IOSchedulingClass = "idle";
      IOWeight = 20;
      OOMScoreAdjust = 500;
    };
  };
}
