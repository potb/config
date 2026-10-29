{...}: {
  nixos = {};
  darwin = {};
  home = {
    programs.herdr = {
      enable = true;
      settings = {
        onboarding = false;
        theme.name = "catppuccin-latte";
        terminal.kitty_graphics = true;
        update = {
          version_check = false;
          manifest_check = false;
        };
      };
    };
  };
}
