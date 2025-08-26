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
  };

  outputs = {
    self,
    nixpkgs,
    home-manager,
    nix-darwin,
    ...
  } @ inputs: let
    inherit (self) outputs;
    systems = [
      "x86_64-linux"
      "aarch64-darwin"
    ];
    forAllSystems = nixpkgs.lib.genAttrs systems;
    
    # Helper function to get home-manager modules for a platform
    getHomeManagerModules = platform: let
      allModules = map (name: import (./home-manager/modules + "/${name}")) (
        builtins.filter (name: builtins.match ".+\\.nix$" name != null) (
          builtins.attrNames (builtins.readDir ./home-manager/modules)
        )
      );
      # Filter modules based on platform
      platformModules = 
        if platform == "linux" then [
          ./home-manager/modules/core.nix
          ./home-manager/modules/linux.nix
        ]
        else if platform == "darwin" then [
          ./home-manager/modules/core.nix
          ./home-manager/modules/darwin.nix
        ]
        else [
          ./home-manager/modules/core.nix
        ];
    in [
      ./home-manager/home.nix
      ./home-manager/modules/home.nix
    ] ++ platformModules;
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
        modules =
          nixosModules
          ++ [
            ./nixos/configuration.nix
            inputs.home-manager.nixosModules.home-manager

            {
              home-manager.useGlobalPkgs = true;
              home-manager.useUserPackages = true;
              home-manager.sharedModules = [];
              home-manager.extraSpecialArgs = {
                inherit inputs;
                system = "x86_64-linux";
              };

              home-manager.users.potb = {
                imports = getHomeManagerModules "linux";
                home.homeDirectory = "/home/potb";
              };
            }
          ];
      };
    };

    darwinConfigurations = {
      nyx = nix-darwin.lib.darwinSystem {
        specialArgs = {inherit inputs outputs;};
        modules = [
          ./darwin/configuration.nix
          inputs.home-manager.darwinModules.home-manager

          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.sharedModules = [];
            home-manager.extraSpecialArgs = {
              inherit inputs;
            };

            home-manager.users.potb = {
              imports = getHomeManagerModules "darwin";
              home.homeDirectory = "/Users/potb";
            };
          }
        ];
      };
    };
  };
}
