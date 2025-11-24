{
  config,
  pkgs,
  ...
}: {
  system.activationScripts.applications.text = let
    apps = pkgs.buildEnv {
      name = "applications";
      paths = config.environment.systemPackages;
      pathsToLink = [ "/Applications" ];
    };
  in ''
    mkdir -p /Applications/Nix\ Apps
    /usr/bin/find ${apps}/Applications -maxdepth 1 -name "*.app" -type d -print0 | \
      xargs -0 -I{} /bin/ln -sf "{}" /Applications/Nix\ Apps/
  '';

  system.activationScripts.extraActivation.text = ''
    softwareupdate --install-rosetta --agree-to-license
  '';
}
