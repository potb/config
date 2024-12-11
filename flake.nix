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

    nh = {
      url = "github:viperML/nh";
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
            ]
            ++ extraModules;
        };
    in
      {
        "potb@charon" = mkHomeConfig {
          system = "x86_64-linux";
        };
      };
  };
}
