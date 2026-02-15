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
  };

  outputs = {
    self,
    nixpkgs,
    home-manager,
    nix-darwin,
    nix-rosetta-builder,
    nix-homebrew,
    ...
  } @ inputs: let
    inherit (self) outputs;
    systems = [
      "x86_64-linux"
      "aarch64-darwin"
    ];
    forAllSystems = nixpkgs.lib.genAttrs systems;

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
        |> map (name: import (overlaysDir + "/${name}"))
      else [];

    getHomeManagerModules = platform: let
      modulesDir = ./home-manager/modules;
      platformDir = modulesDir + "/${platform}";

      loadNixPaths = dir:
        builtins.readDir dir
        |> builtins.attrNames
        |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
        |> map (name: dir + "/${name}");

      sharedModules = loadNixPaths modulesDir;
      platformModules =
        if builtins.pathExists platformDir
        then loadNixPaths platformDir
        else [];
    in
      sharedModules ++ platformModules;

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
          ++ [
            ./nixos/configuration.nix
            inputs.home-manager.nixosModules.home-manager

            {
              nixpkgs.overlays = nixosAllOverlays;

              home-manager.useGlobalPkgs = true;
              home-manager.useUserPackages = true;
              home-manager.sharedModules = [];
              home-manager.extraSpecialArgs = {
                inherit inputs;
              };

              home-manager.backupFileExtension = "backup";

              home-manager.users.potb = {
                imports = getHomeManagerModules "linux";
                home.homeDirectory = nixpkgs.lib.mkForce "/home/potb";
              };
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
          ++ [
            ./darwin/configuration.nix
            inputs.home-manager.darwinModules.home-manager
            nix-rosetta-builder.darwinModules.default
            nix-homebrew.darwinModules.nix-homebrew

            {
              nixpkgs.overlays = darwinAllOverlays;

              nix-rosetta-builder.enable = true;
              nix-rosetta-builder.onDemand = true;

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
              home-manager.sharedModules = [];
              home-manager.extraSpecialArgs = {
                inherit inputs;
              };

              home-manager.users.potb = {
                imports = getHomeManagerModules "darwin";
                home.homeDirectory = nixpkgs.lib.mkForce "/Users/potb";
              };
            }
          ];
      };
    };
  };
}
