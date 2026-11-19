{
  home-manager.users.potb = {config, ...}: {
    sops = {
      age.keyFile = "${config.home.homeDirectory}/.config/sops/age/keys.txt";
      defaultSopsFile = ../../../secrets/herdr.yaml;
      secrets.linear-key.path = "${config.home.homeDirectory}/.config/herdr-app/data/linear/key";
      secrets.herdr-ship-repo = {
        sopsFile = ../../../secrets/private.yaml;
        key = "ship-repo";
        path = "${config.home.homeDirectory}/.config/herdr-app/data/ship-repo.json";
      };
    };
  };
}
