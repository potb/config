{...}: {
  nixos = {};
  darwin = {};
  home = {
    programs.herdr = {
      enable = true;
      settings = {
        onboarding = false;
        theme.name = "catppuccin-latte";
        update = {
          version_check = false;
          manifest_check = false;
        };
      };
    };
  };
}
