{...}: {
  services.gnome.gnome-keyring.enable = true;

  programs._1password.enable = true;
  programs._1password-gui = {
    enable = true;
    polkitPolicyOwners = ["potb"];
  };
}
