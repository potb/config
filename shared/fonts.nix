{pkgs}: {
  monospace = {
    package = pkgs.nerd-fonts.fira-code;
    name = "FiraCode Nerd Font Mono";
  };
  ui = {
    package = pkgs.inter;
    name = "Inter";
  };
  serif = {
    package = pkgs.liberation_ttf;
    name = "Liberation Serif";
  };
  emoji = {
    package = pkgs.nerd-fonts.symbols-only;
    name = "Symbols Nerd Font";
  };
  sizes = let
    values = {
      small = 10;
      medium = 12;
      large = 14;
    };
  in
    values // {str = builtins.mapAttrs (_: toString) values;};
}
