{
  description = "NixOS and nix-darwin configuration for charon, nyx and new-horizons";

  nixConfig = {
    extra-substituters = ["https://potb.cachix.org"];
    extra-trusted-public-keys = ["potb.cachix.org-1:byvGn6qmFOaccjc7kbUMNKLJaCyn/B8HqGNG4gxI6P0="];
  };

  inputs = {
    nixpkgs = {
      url = "github:NixOS/nixpkgs/nixos-unstable";
    };

    nixpkgs-master = {
      url = "github:NixOS/nixpkgs/master";
    };

    opencode-src = {
      url = "github:anomalyco/opencode/production";
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

    schemastore = {
      url = "github:SchemaStore/schemastore";
      flake = false;
    };

    opencode-oh-my-openagent = {
      url = "github:code-yeongyu/oh-my-openagent";
      flake = false;
    };

    opencode-anthropic-auth = {
      url = "github:ex-machina-co/opencode-anthropic-auth";
      flake = false;
    };

    opencode-dcp = {
      url = "github:Opencode-DCP/opencode-dynamic-context-pruning";
      flake = false;
    };

    superpowers = {
      url = "github:obra/superpowers";
      flake = false;
    };

    mattpocock-skills = {
      url = "github:mattpocock/skills";
      flake = false;
    };

    stop-slop = {
      url = "github:hardikpandya/stop-slop";
      flake = false;
    };

    agentmemory = {
      url = "github:rohitg00/agentmemory";
      flake = false;
    };

    rtk = {
      url = "github:rtk-ai/rtk";
      flake = false;
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

    codebase-memory-mcp = {
      url = "github:DeusData/codebase-memory-mcp";
    };

    sem = {
      url = "github:ataraxy-labs/sem";
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

    loadUnifiedModules = platform: modulesDir:
      builtins.readDir modulesDir
      |> builtins.attrNames
      |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
      |> map (
        name: let
          file = modulesDir + "/${name}";

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

    # Module sets a host can opt into. `common` is everything a machine needs
    # to be usable over a terminal, and is the only set a headless server
    # takes. The others layer on top.
    moduleSets = {
      common = ./modules/common;
      desktop = ./modules/desktop;
      server = ./modules/server;
      darwin-only = ./modules/darwin-only;
    };

    # A host names the module sets it wants instead of inheriting whatever
    # happens to live in a directory. Adding a machine means adding an entry
    # here and a directory under ./hosts.
    mkHost = {
      hostname,
      system,
      platform,
      sets ? ["common"],
      extraModules ? [],
      homeDirectory,
    }: let
      unified = builtins.concatLists (
        map (name: loadUnifiedModules platform moduleSets.${name}) sets
      );

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
    });

    nixosConfigurations = {
      charon = mkHost {
        hostname = "charon";
        system = "x86_64-linux";
        platform = "nixos";
        sets = [
          "common"
          "desktop"
        ];
        homeDirectory = "/home/potb";
        extraModules = [
          disko.nixosModules.disko
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
          "common"
          "server"
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
          "common"
          "desktop"
          "darwin-only"
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
                "rtk-ai/tap"
              ];
            };
          }
        ];
      };
    };
  };
}
