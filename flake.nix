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

    nix-darwin = {
      url = "github:LnL7/nix-darwin";
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
    
    # Helper function to find all .nix modules in a directory
    findModules = dir:
      map (name: import (dir + "/${name}")) (
        builtins.filter (name: builtins.match ".+\\.nix$" name != null) (
          builtins.attrNames (builtins.readDir dir)
        )
      );
    
    # Helper function to get home-manager modules (common + platform-specific)
    getHomeManagerModules = platform:
      let
        commonModules = findModules ./home-manager/modules/common;
        platformModules = findModules (./home-manager/modules + "/${platform}");
      in
        commonModules ++ platformModules;
  in {
    formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);

    # TODO: Use pipes when alejandra supports it
    nixosConfigurations = let
      nixosModules = findModules ./nixos/modules;
    in {
      charon = nixpkgs.lib.nixosSystem {
        specialArgs = {inherit inputs outputs;};
        modules = nixosModules ++ [
          ./nixos/configuration.nix
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.extraSpecialArgs = {inherit inputs outputs;};
            home-manager.users.potb = {
              imports = with inputs; [
                catppuccin.homeModules.catppuccin
              ] ++ (getHomeManagerModules "linux");
            };
          }
        ];
      };
    };

    darwinConfigurations = let
      darwinModules = findModules ./darwin/modules;
    in {
      nyx = nix-darwin.lib.darwinSystem {
        specialArgs = {inherit inputs outputs;};
        modules = darwinModules ++ [
          ./darwin/configuration.nix
          home-manager.darwinModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.extraSpecialArgs = {inherit inputs outputs;};
            home-manager.users.potb = {
              imports = with inputs; [
                catppuccin.homeModules.catppuccin
              ] ++ (getHomeManagerModules "mac");
            };
          }
        ];
      };
    };

    homeConfigurations = let
      # Helper function to infer platform from system string
      inferPlatform = system:
        if builtins.match ".*linux.*" system != null
        then "linux"
        else if builtins.match ".*darwin.*" system != null
        then "mac"
        else throw "Unknown platform for system: ${system}";
      
      mkHomeConfig = {system}:
        let
          platform = inferPlatform system;
        in
          home-manager.lib.homeManagerConfiguration {
            pkgs = nixpkgs.legacyPackages.${system};
            extraSpecialArgs = {inherit inputs outputs system;};
            modules = with inputs;
              [
                catppuccin.homeModules.catppuccin
              ]
              ++ (getHomeManagerModules platform);
          };
    in {
      "potb@charon" = mkHomeConfig {
        system = "x86_64-linux";
      };

      "potb@nyx" = mkHomeConfig {
        system = "aarch64-darwin";
      };
    };
  };
}
