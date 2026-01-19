{
  description = "Your new nix config";

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

    catppuccin-zsh-syntax-highlighting = {
      url = "github:catppuccin/zsh-syntax-highlighting";
      flake = false;
    };

    catppuccin-bat = {
      url = "github:catppuccin/bat";
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

    nix-rosetta-builder = {
      url = "github:cpick/nix-rosetta-builder";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Cursor PR for version 2.3.29 (not yet merged to unstable)
    nixpkgs-cursor-pr = {
      url = "github:NixOS/nixpkgs/pull/478688/head";
    };
  };

  outputs = {
    self,
    nixpkgs,
    home-manager,
    nix-darwin,
    nix-rosetta-builder,
    ...
  } @ inputs: let
    inherit (self) outputs;
    systems = [
      "x86_64-linux"
      "aarch64-darwin"
    ];
    forAllSystems = nixpkgs.lib.genAttrs systems;

    # Overlay to use cursor from PR #478688
    cursorPROverlay = final: prev: let
      prPkgs = import inputs.nixpkgs-cursor-pr {
        system = prev.stdenv.hostPlatform.system;
        config.allowUnfree = true;
      };
    in {
      code-cursor-fhs = prPkgs.code-cursor-fhs;
      code-cursor = prPkgs.code-cursor;
    };

    # Helper to load all .nix modules from a directory
    loadModulesFromDir = moduleDir:
      builtins.readDir moduleDir
      |> builtins.attrNames
      |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
      |> map (name: import (moduleDir + "/${name}"));

    # Helper to load all overlay files from overlays directory
    loadOverlays = overlaysDir:
      if builtins.pathExists overlaysDir
      then
        builtins.readDir overlaysDir
        |> builtins.attrNames
        |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
        |> map (name: import (overlaysDir + "/${name}"))
      else [];

    # Helper function to get home-manager modules for a platform
    getHomeManagerModules = platform:
      {
        linux = [./home-manager/modules/core.nix ./home-manager/modules/linux.nix];
        darwin = [./home-manager/modules/core.nix ./home-manager/modules/darwin.nix];
      }
      .${
        platform
      }
      or [
        ./home-manager/modules/core.nix
      ]
      |> (platformModules:
        [
          ./home-manager/home.nix
          ./home-manager/modules/home.nix
        ]
        ++ platformModules);

    # Load overlays per category
    sharedOverlays = loadOverlays ./overlays;
    darwinOverlays = loadOverlays ./darwin/overlays;
    nixosOverlays = loadOverlays ./nixos/overlays;

    # Combine overlays per system (shared first, then system-specific)
    darwinAllOverlays = [cursorPROverlay] ++ sharedOverlays ++ darwinOverlays;
    nixosAllOverlays = [cursorPROverlay] ++ sharedOverlays ++ nixosOverlays;
  in {
    formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);

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

            {
              nixpkgs.overlays = darwinAllOverlays;

              nix-rosetta-builder.enable = true;
              nix-rosetta-builder.onDemand = true;

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
