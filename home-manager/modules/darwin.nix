{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:
{
  stylix.targets.xresources.enable = false;

  home.packages = with pkgs; [
    code-cursor
    raycast

    stdenv.cc
    gnumake
    autoconf
    automake
    libtool
    pkg-config
  ];

  home.activation.linkHomeManagerApps = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
    appsDir="$HOME/Applications/Home Manager Apps"
    $DRY_RUN_CMD mkdir -p "$appsDir"

    homeAppsPath="$HOME/.local/state/home-manager/gcroots/current-home/home-path/Applications"

    $DRY_RUN_CMD find "$appsDir" -maxdepth 1 -type f -name "*.app" -delete 2>/dev/null || true

    if [ -d "$homeAppsPath" ]; then
      echo "Linking home-manager apps from $homeAppsPath to $appsDir..."
      for app in "$homeAppsPath"/*.app; do
        if [ -e "$app" ]; then
          appName=$(basename "$app")
          $DRY_RUN_CMD ${pkgs.mkalias}/bin/mkalias "$app" "$appsDir/$appName"
        fi
      done
    fi
  '';

  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";

    CC = "${pkgs.stdenv.cc}/bin/cc";
    CXX = "${pkgs.stdenv.cc}/bin/c++";
  };
}
