{
  description = "NixOS and nix-darwin configuration for charon, kerberos, nyx and new-horizons";

  nixConfig = {
    extra-substituters = [
      "https://potb.cachix.org"
      "https://hyprland.cachix.org"
    ];
    extra-trusted-public-keys = [
      "potb.cachix.org-1:byvGn6qmFOaccjc7kbUMNKLJaCyn/B8HqGNG4gxI6P0="
      "hyprland.cachix.org-1:a7pgxzMz7+chwVL3/pzj6jIBMioiJM7ypFP8PwtkuGc="
    ];
  };

  inputs = {
    nixpkgs = {
      url = "github:NixOS/nixpkgs/nixos-unstable";
    };

    determinate = {
      url = "https://flakehub.com/f/DeterminateSystems/determinate/*";
    };

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nix-darwin = {
      url = "github:LnL7/nix-darwin";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    catppuccin-delta = {
      url = "github:catppuccin/delta";
      flake = false;
    };

    stylix = {
      url = "github:nix-community/stylix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nh = {
      url = "github:nix-community/nh";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Pinned: newer commits (post aca4b8b) chase a Hyprland header layout
    # that predates hy3's own bundled hyprland input pin (build breaks with
    # "hyprland/src/desktop/view/window/Window.hpp: No such file"). Bump
    # once upstream re-syncs their hyprland pin with their source.
    hy3.url = "github:outfoxxed/hy3/aca4b8bf4702f2b7bbc3d032b0206265a282c8af";

    nix-rosetta-builder = {
      url = "github:cpick/nix-rosetta-builder";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nix-homebrew = {
      url = "github:zhaofengli/nix-homebrew";
    };

    homebrew-core = {
      url = "github:homebrew/homebrew-core";
      flake = false;
    };

    homebrew-cask = {
      url = "github:homebrew/homebrew-cask";
      flake = false;
    };

    dnscrypt-resolvers = {
      url = "github:DNSCrypt/dnscrypt-resolvers";
      flake = false;
    };

    nixvim = {
      url = "github:nix-community/nixvim";
    };

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nix-openclaw = {
      url = "github:openclaw/nix-openclaw";
    };

    qwerty-fr = {
      url = "github:qwerty-fr/qwerty-fr/v0.7.3";
      flake = false;
    };

    agent-browser = {
      url = "github:vercel-labs/agent-browser/v0.31.1";
      flake = false;
    };

    tsm-app = {
      url = "github:exceptionptr/tsm-app-linux/v1.1.15";
      flake = false;
    };

    nixos-apple-silicon = {
      url = "github:nix-community/nixos-apple-silicon/1bf1838b982768c3ece6d719f03e13b9f7408e6d";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    home-manager,
    nix-darwin,
    nix-rosetta-builder,
    nix-homebrew,
    disko,
    ...
  } @ inputs: let
    inherit (self) outputs;
    systems = [
      "x86_64-linux"
      "aarch64-darwin"
      "aarch64-linux"
    ];
    forAllSystems = nixpkgs.lib.genAttrs systems;
    lib = nixpkgs.lib;

    loadModulesFromDir = moduleDir:
      builtins.readDir moduleDir
      |> builtins.attrNames
      |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
      |> map (name: import (moduleDir + "/${name}"));

    loadOverlays = overlaysDir:
      if builtins.pathExists overlaysDir
      then
        builtins.readDir overlaysDir
        |> builtins.attrNames
        |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
        |> map (name: import (overlaysDir + "/${name}") {inherit inputs lib;})
      else [];

    staticArgs = file: let
      unavailable = name:
        builtins.throw "${name} read during static import of ${toString file}; move that read inside the nixos, darwin or home attribute";
    in {
      inherit lib inputs;
      pkgs = unavailable "pkgs";
      config = unavailable "config";
      options = unavailable "options";
      modulesPath = unavailable "modulesPath";
    };

    listNixFilesRecursive = platform: dir: let
      platformDirs = ["linux" "darwin"];
      wanted =
        if platform == "nixos"
        then "linux"
        else "darwin";

      entries = builtins.readDir dir;

      go = name: type: let
        path = dir + "/${name}";
      in
        if type == "directory"
        then
          if builtins.elem name platformDirs
          then
            if name == wanted
            then listNixFilesRecursive platform path
            else []
          else listNixFilesRecursive platform path
        else if builtins.match ".+\\.nix$" name != null
        then [path]
        else [];
    in
      entries
      |> builtins.attrNames
      |> map (name: go name entries.${name})
      |> builtins.concatLists;

    packageRequestsOf = platform: modulesDir:
      listNixFilesRecursive platform modulesDir
      |> map (file: (import file (staticArgs file)).packages or [])
      |> builtins.concatLists;

    loadUnifiedModules = platform: modulesDir:
      listNixFilesRecursive platform modulesDir
      |> map (
        file: let
          modStatic = import file (staticArgs file);

          staticPlatform = modStatic.${platform} or {};
          staticImports = staticPlatform.imports or [];
          hasHome = modStatic ? home;
        in
          args @ {
            pkgs,
            lib,
            inputs,
            ...
          }: let
            hmModule = hmArgs @ {
              lib,
              inputs,
              ...
            }: {
              config = let
                realArgs =
                  hmArgs
                  // {
                    inherit pkgs;
                  };
                mod = import file realArgs;
                homeAttr = mod.home or null;

                homeResolved =
                  if homeAttr == null
                  then {}
                  else if builtins.isFunction homeAttr
                  then homeAttr realArgs
                  else homeAttr;

                platformKey =
                  if platform == "nixos"
                  then "linux"
                  else "darwin";

                sharedConfig = builtins.removeAttrs homeResolved [
                  "linux"
                  "darwin"
                ];

                platformAttr = homeResolved.${platformKey} or null;
                platformConfig =
                  if platformAttr == null
                  then {}
                  else if builtins.isFunction platformAttr
                  then platformAttr realArgs
                  else platformAttr;
              in
                lib.mkMerge [
                  sharedConfig
                  platformConfig
                ];
            };
          in {
            imports = staticImports;
            config = let
              mod = import file args;
              platformConfig = mod.${platform} or {};
              platformConfigClean = builtins.removeAttrs platformConfig ["imports"];
            in
              platformConfigClean
              // lib.optionalAttrs hasHome {
                home-manager.users.potb = {
                  imports = [hmModule];
                };
              };
          }
      );

    sharedOverlays = loadOverlays ./overlays;
    nixosAllOverlays = sharedOverlays;
    darwinAllOverlays = sharedOverlays;

    moduleSets = {
      base = ./modules/base;
      linux = ./modules/linux;
      gui = ./modules/gui;
      desktop-apps = ./modules/desktop-apps;
      leisure = ./modules/leisure;
      workstation = ./modules/workstation;
      laptop = ./modules/laptop;
      dev = ./modules/dev;
      containers = ./modules/containers;
      agents = ./modules/agents;
      tailscale = ./modules/tailscale;
      exit-node = ./modules/exit-node;
      exit-node-client = ./modules/exit-node-client;
      hardened = ./modules/hardened;
      lan = ./modules/lan;
      openclaw = ./modules/apps/openclaw;
      darwin = ./modules/darwin;
    };

    # A host names the module sets it wants instead of inheriting whatever
    # happens to live in a directory. Adding a machine means adding an entry
    # here and a directory under ./hosts.
    mkHost = {
      hostname,
      system,
      platform,
      sets ? ["common"],
      channels ? {},
      extraModules ? [],
      homeDirectory,
    }: let
      unified = builtins.concatLists (
        map (name: loadUnifiedModules platform moduleSets.${name}) sets
      );

      requestedPackages = builtins.concatLists (
        map (name: packageRequestsOf platform moduleSets.${name}) sets
      );

      channelModule = {pkgs, ...}: let
        resolved = import ./modules/lib/resolve-channels.nix {
          inherit lib pkgs platform;
          requests = let
            requested = builtins.listToAttrs (
              map (name: lib.nameValuePair name true) requestedPackages
            );

            stray = builtins.attrNames (builtins.removeAttrs channels (builtins.attrNames requested));
          in
            if stray != []
            then
              builtins.throw ''
                host ${hostname} selects a channel for a package no trait asked for:
                  ${lib.concatStringsSep "\n  " stray}
              ''
            else requested // channels;
        };
      in {
        config = lib.mkMerge [
          resolved.${platform}
          {
            assertions = resolved.availabilityAssertions;
            home-manager.users.potb = resolved.home;
          }
        ];
      };

      hostModules =
        if builtins.pathExists (./hosts + "/${hostname}/modules")
        then loadModulesFromDir (./hosts + "/${hostname}/modules")
        else [];

      hostConfiguration = ./hosts + "/${hostname}/configuration.nix";

      builder =
        if platform == "nixos"
        then nixpkgs.lib.nixosSystem
        else nix-darwin.lib.darwinSystem;

      homeManagerModule =
        if platform == "nixos"
        then inputs.home-manager.nixosModules.home-manager
        else inputs.home-manager.darwinModules.home-manager;

      overlays =
        if platform == "nixos"
        then nixosAllOverlays
        else darwinAllOverlays;
    in
      builder {
        specialArgs = {inherit inputs outputs;};
        modules =
          unified
          ++ [channelModule]
          ++ hostModules
          ++ lib.optional (builtins.pathExists hostConfiguration) hostConfiguration
          ++ [
            homeManagerModule
            {
              nixpkgs.overlays = overlays;
              networking.hostName = lib.mkDefault hostname;

              home-manager.useGlobalPkgs = true;
              home-manager.useUserPackages = true;
              home-manager.sharedModules = [
                inputs.nixvim.homeModules.nixvim
              ];
              home-manager.extraSpecialArgs = {inherit inputs;};
              home-manager.backupFileExtension = "backup";
              home-manager.users.potb.home.homeDirectory =
                nixpkgs.lib.mkForce homeDirectory;
            }
          ]
          ++ extraModules;
      };
  in {
    formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);

    checks = forAllSystems (system: {
      package-channels = let
        pkgs = nixpkgs.legacyPackages.${system};

        hosts =
          lib.mapAttrs (_: h: {
            inherit (h) config;
            platform = "nixos";
          })
          self.nixosConfigurations
          // lib.mapAttrs (_: h: {
            inherit (h) config;
            platform = "darwin";
          })
          self.darwinConfigurations;

        nameOf = p: p.pname or (p.name or "<unnamed>");

        brewNames = host:
          lib.optionals (host.platform == "darwin") (
            map (c: c.name) host.config.homebrew.casks
            ++ map (b: b.name) host.config.homebrew.brews
          );

        nixNames = host:
          map nameOf (
            host.config.home-manager.users.potb.home.packages
            ++ host.config.environment.systemPackages
            ++ host.config.fonts.packages
          );

        aliases = {
          ghostty = ["ghostty" "ghostty-bin"];
          "1password-cli" = ["_1password-cli" "1password-cli"];
          google-chrome = ["google-chrome"];
          slack = ["slack"];
          spotify = ["spotify"];
          discord = ["discord"];
          "qwerty-fr" = ["qwerty-fr" "qwertyFr"];
          tailscale = ["tailscale" "tailscale-app"];
          "font-fira-code-nerd-font" = ["nerd-fonts-fira-code"];
          "font-inter" = ["inter"];
          "font-symbols-only-nerd-font" = ["nerd-fonts-symbols-only"];
        };

        duplicatesOn = hostName: host: let
          brews = brewNames host;
          nixed = nixNames host;

          both =
            lib.filterAttrs (
              logical: names:
                (builtins.any (n: builtins.elem n brews) (names ++ [logical]))
                && (builtins.any (n: builtins.elem n nixed) names)
            )
            aliases;
        in
          map (logical: "${hostName}: ${logical} arrives from both Homebrew and nixpkgs") (
            builtins.attrNames both
          );

        problems = builtins.concatLists (lib.mapAttrsToList duplicatesOn hosts);
      in
        if problems != []
        then
          throw ''
            a package arrives through two channels at once:
              ${lib.concatStringsSep "\n  " problems}
          ''
        else pkgs.runCommand "package-channels-check" {} "touch $out";

      trait-table = let
        pkgs = nixpkgs.legacyPackages.${system};
      in
        pkgs.runCommand "trait-table-check" {
          nativeBuildInputs = [pkgs.python3];
          readme = ./README.md;
          flake = ./flake.nix;
        } ''
          python3 ${./scripts/check-trait-table.py} "$flake" "$readme"
          touch $out
        '';

      kerberos-offhost = let
        pkgs = nixpkgs.legacyPackages.${system};

        stubFirmware = {
          lib,
          pkgs,
          ...
        }: {
          hardware.asahi.peripheralFirmwareDirectory =
            lib.mkForce
            (pkgs.runCommand "stub-vendor-firmware" {} "mkdir -p $out; touch $out/firmware.cpio");
        };

        kerberos =
          (self.nixosConfigurations.kerberos.extendModules {
            modules = [stubFirmware];
          })
          .config;

        unavailable = packages:
          map (p: p.name or "<unnamed>") (
            builtins.filter (p: !(p.meta.available or true)) packages
          );

        acknowledgedUpstreamWarnings = [
          {
            match = "programs.rofi.font";
            reason = "stylix sets the renamed option itself, see docs/upstream-warnings.md";
          }
        ];

        containsLiteral = needle: haystack:
          builtins.length (builtins.split (lib.escapeRegex needle) haystack) > 1;

        acknowledged = warning:
          builtins.any (a: containsLiteral a.match warning) acknowledgedUpstreamWarnings;

        staleAcknowledgements =
          builtins.filter (
            a: !(builtins.any (containsLiteral a.match) kerberos.warnings)
          )
          acknowledgedUpstreamWarnings;

        problems =
          map (a: "assertion: ${a.message}") (
            builtins.filter (a: !a.assertion) kerberos.assertions
          )
          ++ map (w: "warning: ${w}") (
            builtins.filter (w: !(acknowledged w)) kerberos.warnings
          )
          ++ map (
            a: "stale acknowledgement, upstream fixed ${a.match}, drop it from flake.nix: ${a.reason}"
          )
          staleAcknowledgements
          ++ map (n: "no aarch64-linux build: ${n}") (
            unavailable kerberos.home-manager.users.potb.home.packages
            ++ unavailable kerberos.environment.systemPackages
            ++ unavailable kerberos.fonts.packages
          );
      in
        if problems != []
        then
          throw ''
            nixosConfigurations.kerberos:
              ${lib.concatStringsSep "\n  " problems}
          ''
        else
          pkgs.runCommand "kerberos-offhost-check" {
            evaluated = builtins.unsafeDiscardStringContext kerberos.system.build.toplevel.drvPath;
          } "echo \"$evaluated\" > $out";

      deadnix =
        nixpkgs.legacyPackages.${system}.runCommand "deadnix-check"
        {
          nativeBuildInputs = [nixpkgs.legacyPackages.${system}.deadnix];
        }
        ''
          cd ${self}
          deadnix --fail --no-lambda-pattern-names --no-lambda-arg
          touch $out
        '';

      openclaw-config = let
        pkgs = nixpkgs.legacyPackages.${system};
        gateway = self.nixosConfigurations.new-horizons.config.services.openclaw-gateway;
        generated = pkgs.writeText "openclaw-config.json" (
          builtins.unsafeDiscardStringContext (builtins.toJSON gateway.config)
        );
      in
        pkgs.runCommand "openclaw-config-check"
        {
          nativeBuildInputs = [
            pkgs.python3
          ];
        }
        ''
          gzip -dc ${./checks/openclaw-config-schema.json.gz} > schema.json
          python3 ${./scripts/validate-openclaw-config.py} ${generated} schema.json
          touch $out
        '';

      openclaw-schema-current = let
        pkgs = nixpkgs.legacyPackages.${system};
        gateway = self.nixosConfigurations.new-horizons.config.services.openclaw-gateway;
      in
        if system != gateway.package.stdenv.hostPlatform.system
        then pkgs.runCommand "openclaw-schema-current-skipped" {} "touch $out"
        else
          pkgs.runCommand "openclaw-schema-current-check"
          {
            nativeBuildInputs = [
              pkgs.python3
              gateway.package
            ];
          }
          ''
            export HOME=$TMPDIR
            openclaw config schema > live.json
            gzip -dc ${./checks/openclaw-config-schema.json.gz} > pinned.json
            python3 ${./scripts/compare-openclaw-schema.py} pinned.json live.json
            touch $out
          '';
    });

    nixosConfigurations = {
      charon = mkHost {
        hostname = "charon";
        system = "x86_64-linux";
        platform = "nixos";
        sets = [
          "base"
          "linux"
          "gui"
          "desktop-apps"
          "leisure"
          "workstation"
          "dev"
          "containers"
          "agents"
          "lan"
          "tailscale"
          "exit-node"
        ];
        homeDirectory = "/home/potb";
        extraModules = [
          disko.nixosModules.disko
        ];
      };

      kerberos = mkHost {
        hostname = "kerberos";
        system = "aarch64-linux";
        platform = "nixos";
        sets = [
          "base"
          "linux"
          "gui"
          "desktop-apps"
          "laptop"
          "dev"
          "agents"
          "lan"
          "tailscale"
          "exit-node"
        ];
        channels = {
          slack = "none";
        };
        homeDirectory = "/home/potb";
        extraModules = [
          inputs.nixos-apple-silicon.nixosModules.apple-silicon-support
          {
            nixpkgs.overlays = [
              inputs.nixos-apple-silicon.overlays.apple-silicon-overlay
            ];
          }
        ];
      };

      # Headless VPS hosting the OpenClaw assistant. Takes `common` for a
      # working shell and `server` for everything the agent needs; no desktop
      # set, so nothing pulls in a graphical stack.
      new-horizons = mkHost {
        hostname = "new-horizons";
        system = "x86_64-linux";
        platform = "nixos";
        sets = [
          "base"
          "linux"
          "hardened"
          "tailscale"
          "exit-node-client"
          "openclaw"
        ];
        homeDirectory = "/home/potb";
        extraModules = [
          disko.nixosModules.disko
          inputs.sops-nix.nixosModules.sops
          inputs.nix-openclaw.nixosModules.openclaw-gateway
        ];
      };
    };

    darwinConfigurations = {
      nyx = mkHost {
        hostname = "nyx";
        system = "aarch64-darwin";
        platform = "darwin";
        sets = [
          "base"
          "gui"
          "desktop-apps"
          "leisure"
          "dev"
          "containers"
          "agents"
          "lan"
          "tailscale"
          "darwin"
        ];
        homeDirectory = "/Users/potb";
        extraModules = [
          inputs.determinate.darwinModules.default
          nix-homebrew.darwinModules.nix-homebrew
          {
            nix-homebrew = {
              enable = true;
              enableRosetta = true;
              user = "potb";

              # nyx had Homebrew installed by the official script before this
              # flake managed it. Without autoMigrate, activation aborts on
              # the pre-existing /opt/homebrew prefix.
              autoMigrate = true;
              taps = {
                "homebrew/homebrew-core" = inputs.homebrew-core;
                "homebrew/homebrew-cask" = inputs.homebrew-cask;
              };

              # nyx taps a handful of third-party repositories for software
              # that exists nowhere else: aerospace, the AlloyDB proxy and
              # a few single-formula taps. Fully declarative taps would
              # replace the whole directory with the two above and take
              # those with it, so the rest stay imperative until they are
              # pinned as inputs of their own.
              mutableTaps = true;

              # `brew shellenv` puts /opt/homebrew/bin ahead of the Nix
              # profile in every interactive shell, so a tool this
              # configuration declares loses to whatever Homebrew happens
              # to have installed under the same name. The launcher in
              # /run/current-system/sw/bin is enough to run brew itself,
              # and hosts/nyx/modules/homebrew.nix appends the prefix to
              # PATH so brew-only formulae still resolve.
              enableZshIntegration = false;
              enableBashIntegration = false;

              # Homebrew 6.0 refuses to load anything from a tap that has
              # not been trusted. These are the taps whose formulae and
              # casks this configuration installs on purpose.
              trust.taps = [
                "nikitabobko/tap"
                "asmvik/formulae"
                "jaisonerick/tap"
                "potb/tap"
              ];
            };
          }
        ];
      };
    };
  };
}
