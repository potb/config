{
  description = "Your new nix config";

  nixConfig = {
    extra-substituters = [ "https://potb.cachix.org" ];
    extra-trusted-public-keys = [ "potb.cachix.org-1:byvGn6qmFOaccjc7kbUMNKLJaCyn/B8HqGNG4gxI6P0=" ];
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

    nixpkgs-cursor-pr = {
      url = "github:NixOS/nixpkgs/pull/478688/head";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      home-manager,
      nix-darwin,
      nix-rosetta-builder,
      ...
    }@inputs:
    let
      inherit (self) outputs;
      systems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;

      cursorPROverlay =
        final: prev:
        let
          prPkgs = import inputs.nixpkgs-cursor-pr {
            system = prev.stdenv.hostPlatform.system;
            config.allowUnfree = true;
          };
        in
        {
          code-cursor-fhs = prPkgs.code-cursor-fhs;
          code-cursor = prPkgs.code-cursor;
        };

      loadModulesFromDir =
        moduleDir:
        builtins.readDir moduleDir
        |> builtins.attrNames
        |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
        |> map (name: import (moduleDir + "/${name}"));

      loadOverlays =
        overlaysDir:
        if builtins.pathExists overlaysDir then
          builtins.readDir overlaysDir
          |> builtins.attrNames
          |> builtins.filter (name: builtins.match ".+\\.nix$" name != null)
          |> map (name: import (overlaysDir + "/${name}"))
        else
          [ ];

      getHomeManagerModules =
        platform:
        {
          linux = [
            ./home-manager/modules/core.nix
            ./home-manager/modules/linux.nix
          ];
          darwin = [
            ./home-manager/modules/core.nix
            ./home-manager/modules/darwin.nix
          ];
        }
        .${platform} or [
          ./home-manager/modules/core.nix
        ]
        |> (
          platformModules:
          [
            ./home-manager/home.nix
            ./home-manager/modules/home.nix
          ]
          ++ platformModules
        );

      sharedOverlays = loadOverlays ./overlays;
      darwinOverlays = loadOverlays ./darwin/overlays;
      nixosOverlays = loadOverlays ./nixos/overlays;

      darwinAllOverlays = [ cursorPROverlay ] ++ sharedOverlays ++ darwinOverlays;
      nixosAllOverlays = [ cursorPROverlay ] ++ sharedOverlays ++ nixosOverlays;

      mkZedConfig = pkgs: import ./shared/zed.nix { inherit pkgs; };
    in
    {
      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);

      apps = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          zedConfig = mkZedConfig pkgs;
          settingsJson = pkgs.writeText "zed-settings.json" (builtins.toJSON zedConfig.settings);
        in
        {
          zed = {
            type = "app";
            program = "${pkgs.writeShellScript "zed-dev" ''
              CONFIG_DIR=$(mktemp -d)
              mkdir -p "$CONFIG_DIR/zed"
              cp ${settingsJson} "$CONFIG_DIR/zed/settings.json"
              XDG_CONFIG_HOME="$CONFIG_DIR" exec ${pkgs.zed-editor}/bin/zed "$@"
            ''}";
          };
        }
      );

      nixosConfigurations =
        let
          nixosModules = loadModulesFromDir ./nixos/modules;
        in
        {
          charon = nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs; };
            modules = nixosModules ++ [
              ./nixos/configuration.nix
              inputs.home-manager.nixosModules.home-manager

              {
                nixpkgs.overlays = nixosAllOverlays;

                home-manager.useGlobalPkgs = true;
                home-manager.useUserPackages = true;
                home-manager.sharedModules = [ ];
                home-manager.extraSpecialArgs = {
                  inherit inputs mkZedConfig;
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

      darwinConfigurations =
        let
          darwinModules = loadModulesFromDir ./darwin/modules;
        in
        {
          nyx = nix-darwin.lib.darwinSystem {
            specialArgs = { inherit inputs outputs; };
            modules = darwinModules ++ [
              ./darwin/configuration.nix
              inputs.home-manager.darwinModules.home-manager
              nix-rosetta-builder.darwinModules.default

              {
                nixpkgs.overlays = darwinAllOverlays;

                nix-rosetta-builder.enable = true;
                nix-rosetta-builder.onDemand = true;

                home-manager.useGlobalPkgs = true;
                home-manager.useUserPackages = true;
                home-manager.sharedModules = [ ];
                home-manager.extraSpecialArgs = {
                  inherit inputs mkZedConfig;
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
