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
      inputs.nixpkgs.follows = "nixpkgs";
    };

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    schemastore = {
      url = "github:SchemaStore/schemastore";
      flake = false;
    };

    opencode-oh-my-opencode = {
      url = "github:code-yeongyu/oh-my-opencode";
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

          # Static pass: ONLY for platform imports + existence checks.
          # `pkgs` must not be touched while computing imports — throw if accessed.
          modStatic = import file {
            inherit lib inputs;
            pkgs = builtins.throw "pkgs used during static import of ${toString file}";
          };

          staticPlatform = modStatic.${platform} or {};
          staticImports = staticPlatform.imports or [];
          hasHome = modStatic ? home;
        in
          # NixOS/Darwin module wrapper.
          # pkgs is captured here and threaded into hmModule so HM never needs
          # to resolve pkgs from _module.args (avoids infinite recursion with
          # useGlobalPkgs=true).
          args @ {
            pkgs,
            lib,
            inputs,
            ...
          }: let
            # HM module: closes over NixOS `pkgs` so HM's module system never
            # needs to resolve pkgs itself (which would cause infinite recursion).
            hmModule = hmArgs @ {
              lib,
              inputs,
              ...
            }: {
              config = let
                # Inject NixOS pkgs (== HM pkgs with useGlobalPkgs=true).
                realArgs =
                  hmArgs
                  // {
                    inherit pkgs;
                  };
                mod = import file realArgs;
                homeAttr = mod.home or null;
              in
                if homeAttr == null
                then {}
                else if builtins.isFunction homeAttr
                then homeAttr realArgs
                else homeAttr;
            };
          in {
            imports = staticImports;
            config = let
              mod = import file args;
              platformConfig = mod.${platform} or {};
              platformConfigClean = builtins.removeAttrs platformConfig ["imports"];
            in
              # Merge platform config with HM wiring.
              # Use `home-manager.users.potb = { imports = [...]; }` (not
              # `home-manager.users.potb.imports = [...]`) — the latter is not
              # a valid NixOS option; `imports` is a submodule directive.
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
            inputs.determinate.nixosModules.default
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
            # TODO: Re-enable after VM-based linux builder is bootstrapped
            # nix-rosetta-builder.darwinModules.default
            nix-homebrew.darwinModules.nix-homebrew

            {
              nixpkgs.overlays = darwinAllOverlays;

              # nix-rosetta-builder.enable = true;
              # nix-rosetta-builder.onDemand = true;

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
