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
      url = "github:danth/stylix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nh = {
      url = "github:viperML/nh";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nixpkgs-cursor-pr = {
      url = "github:NixOS/nixpkgs/pull/456882/head";
    };

    nix-rosetta-builder = {
      url = "github:cpick/nix-rosetta-builder";
      inputs.nixpkgs.follows = "nixpkgs";
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

    # Helper to load all .nix modules from a directory
    loadModulesFromDir = moduleDir:
      builtins.readDir moduleDir
      |> builtins.attrNames
      |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
      |> map (name: import (moduleDir + "/${name}"));

    # Overlay to use cursor from PR #456882 with version assertion
    cursorPROverlay = final: prev:
      let
        prPkgs = import inputs.nixpkgs-cursor-pr {
          system = prev.stdenv.hostPlatform.system;
          config.allowUnfree = true;
        };
        # Get versions, handling potential attribute name variations
        prVersion = prPkgs.code-cursor-fhs.version or (prPkgs.cursor.version or "0-pr");
        stableVersion = prev.code-cursor-fhs.version or (prev.cursor.version or "0-stable");
        versionCompare = builtins.compareVersions prVersion stableVersion;
      in {
        # FHS variant for Linux (Darwin uses native nixpkgs code-cursor)
        code-cursor-fhs =
          assert builtins.trace "INFO: Cursor PR version: ${prVersion}, nixpkgs unstable version: ${stableVersion}" true;
          assert versionCompare > 0 || builtins.throw ''
            ═══════════════════════════════════════════════════════════════════════
            CURSOR VERSION ASSERTION FAILED
            ═══════════════════════════════════════════════════════════════════════

            PR version:     ${prVersion}
            Untable version: ${stableVersion}

            ═══════════════════════════════════════════════════════════════════════
          '';
          prPkgs.code-cursor-fhs;
      };

    # Helper function to get home-manager modules for a platform
    getHomeManagerModules = platform: let
      allModules =
        builtins.readDir ./home-manager/modules
        |> builtins.attrNames
        |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
        |> map (name: import (./home-manager/modules + "/${name}"));
      # Filter modules based on platform
      platformModules =
        if platform == "linux"
        then [
          ./home-manager/modules/core.nix
          ./home-manager/modules/linux.nix
        ]
        else if platform == "darwin"
        then [
          ./home-manager/modules/core.nix
          ./home-manager/modules/darwin.nix
        ]
        else [
          ./home-manager/modules/core.nix
        ];
    in
      [
        ./home-manager/home.nix
        ./home-manager/modules/home.nix
      ]
      ++ platformModules;
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
              # Apply cursor PR overlay
              nixpkgs.overlays = [cursorPROverlay];

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
              nix-rosetta-builder.enable = true;
              nix-rosetta-builder.onDemand = true;

              # Apply cursor PR overlay
              nixpkgs.overlays = [cursorPROverlay];

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
