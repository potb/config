{
  inputs,
  ...
}: {
  imports = with inputs; [
    stylix.darwinModules.stylix
    ../../shared/modules/theme.nix
  ];
}