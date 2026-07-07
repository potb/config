{
  description = "NixOS and nix-darwin configuration for charon and nyx";

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
      url = "github:viperML/nh";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    hy3.url = "github:outfoxxed/hy3";

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

    caveman = {
      url = "github:JuliusBrussee/caveman";
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

    loadUnifiedModules = platform: modulesDir:
      builtins.readDir modulesDir
      |> builtins.attrNames
      |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
      |> map (
        name: let
          file = modulesDir + "/${name}";

          modStatic = import file {
            inherit lib inputs;
            pkgs = builtins.throw "pkgs used during static import of ${toString file}";
          };

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
    darwinOverlays = loadOverlays ./darwin/overlays;
    nixosOverlays = loadOverlays ./nixos/overlays;

    darwinAllOverlays = sharedOverlays ++ darwinOverlays;
    nixosAllOverlays = sharedOverlays ++ nixosOverlays;
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

    nixosConfigurations = let
      nixosModules = loadModulesFromDir ./nixos/modules;
    in {
      charon = nixpkgs.lib.nixosSystem {
        specialArgs = {inherit inputs outputs;};
        modules =
          nixosModules
          ++ (loadUnifiedModules "nixos" ./modules)
          ++ [
            ./nixos/configuration.nix
            inputs.home-manager.nixosModules.home-manager
            disko.nixosModules.disko

            {
              nixpkgs.overlays = nixosAllOverlays;

              home-manager.useGlobalPkgs = true;
              home-manager.useUserPackages = true;
              home-manager.sharedModules = [
                inputs.nixvim.homeModules.nixvim
              ];
              home-manager.extraSpecialArgs = {
                inherit inputs;
              };

              home-manager.backupFileExtension = "backup";

              home-manager.users.potb.home.homeDirectory = nixpkgs.lib.mkForce "/home/potb";
            }
          ];
      };
    };

    darwinConfigurations = let
      darwinModules = loadModulesFromDir ./darwin/modules;
    in {
      nyx = nix-darwin.lib.darwinSystem {
        specialArgs = {inherit inputs outputs;};
        modules =
          darwinModules
          ++ (loadUnifiedModules "darwin" ./modules)
          ++ [
            ./darwin/configuration.nix
            inputs.determinate.darwinModules.default
            inputs.home-manager.darwinModules.home-manager
            nix-homebrew.darwinModules.nix-homebrew

            {
              nixpkgs.overlays = darwinAllOverlays;

              nix-homebrew = {
                enable = true;
                enableRosetta = true;
                user = "potb";
                taps = {
                  "homebrew/homebrew-core" = inputs.homebrew-core;
                  "homebrew/homebrew-cask" = inputs.homebrew-cask;
                };
                mutableTaps = false;
              };

              home-manager.useGlobalPkgs = true;
              home-manager.useUserPackages = true;
              home-manager.sharedModules = [
                inputs.nixvim.homeModules.nixvim
              ];
              home-manager.extraSpecialArgs = {
                inherit inputs;
              };

              home-manager.users.potb.home.homeDirectory = nixpkgs.lib.mkForce "/Users/potb";
            }
          ];
      };
    };
  };
}
