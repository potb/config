{
  description = "Your new nix config";

  inputs = {
    nixpkgs = {
      url = "github:NixOS/nixpkgs/nixos-unstable";
    };

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nixvim = {
      url = "github:nix-community/nixvim";
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
    };

    catppuccin = {
      url = "github:catppuccin/nix";
    };

    lanzaboote = {
      url = "github:nix-community/lanzaboote/v0.4.1";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    hyprland = {
      url = "github:hyprwm/Hyprland";
    };

    mac-app-util = {
      url = "github:hraban/mac-app-util";
    };

    nix-darwin = {
      url = "github:LnL7/nix-darwin";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nh = {
      url = "github:viperML/nh";
    };

    nixpkgs-master = {
      url = "github:NixOS/nixpkgs/master";
    };
  };

  outputs = {
    self,
    nixpkgs,
    home-manager,
    ...
  } @ inputs: let
    inherit (self) outputs;
    systems = [
      "x86_64-linux"
      "aarch64-darwin"
    ];
    forAllSystems = nixpkgs.lib.genAttrs systems;
  in {
    formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);

    # TODO: Use pipes when alejandra supports it
    nixosConfigurations = let
      nixosModules = map (name: import (./nixos/modules + "/${name}")) (
        builtins.filter (name: builtins.match ".+\\.nix$" name != null) (
          builtins.attrNames (builtins.readDir ./nixos/modules)
        )
      );
    in {
      charon = nixpkgs.lib.nixosSystem {
        specialArgs = {inherit inputs outputs;};
        modules = nixosModules ++ [./nixos/configuration.nix];
      };
    };

    homeConfigurations = let
      mkHomeConfig = {
        system,
        extraModules ? [],
      }:
        home-manager.lib.homeManagerConfiguration {
          pkgs = nixpkgs.legacyPackages.${system};
          extraSpecialArgs = {inherit inputs outputs system;};
          modules = with inputs;
            [
              nixvim.homeManagerModules.nixvim
              catppuccin.homeManagerModules.catppuccin
              ./home-manager/home.nix
              ./home-manager/modules/home.nix
              ./home-manager/modules/text-editor.nix
            ]
            ++ extraModules;
        };
    in
      {
        "potb@charon" = mkHomeConfig {
          system = "x86_64-linux";
        };

        "potb@nyx" = mkHomeConfig {
          system = "aarch64-darwin";
          extraModules = with inputs; [mac-app-util.homeManagerModules.default];
        };
      }
      // {
        "neovim" = home-manager.lib.homeManagerConfiguration {
          pkgs = nixpkgs.legacyPackages.x86_64-linux;
          extraSpecialArgs = {inherit inputs outputs;};
          modules = with inputs; [
            nixvim.homeManagerModules.nixvim
            ./home-manager/modules/home.nix
            ./home-manager/modules/text-editor.nix
          ];
        };
      };

    darwinConfigurations.nyx = inputs.nix-darwin.lib.darwinSystem {
      specialArgs = {inherit inputs outputs;};
      modules = [
        ({
          pkgs,
          lib,
          ...
        }: {
          system.stateVersion = 5;

          nix.package = lib.mkForce pkgs.nixVersions.latest;

          programs.zsh.enable = true;
          environment.shells = [pkgs.zsh];
        })
        ./nixos/modules/nix.nix
      ];
      system = "aarch64-darwin";
    };
  };
}
