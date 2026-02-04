{inputs, ...}: {
  imports = with inputs; [
    stylix.nixosModules.stylix
    ../../shared/modules/theme.nix
  ];
}
