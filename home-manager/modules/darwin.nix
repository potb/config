{
  pkgs,
  lib,
  config,
  inputs,
  ...
}: {
  stylix.targets.xresources.enable = false;

  home.packages = with pkgs; [
    # macOS-specific applications
    # Note: Darwin uses native nixpkgs code-cursor (Linux uses PR overlay code-cursor-fhs)
    code-cursor
    raycast
  ];

  # Custom activation to link apps (similar to mac-app-util behavior)
  home.activation.linkHomeManagerApps = lib.hm.dag.entryAfter ["linkGeneration"] ''
    # Create apps directory
    appsDir="$HOME/Applications/Home Manager Apps"
    $DRY_RUN_CMD mkdir -p "$appsDir"

    # Use the activated generation's home-path
    homeAppsPath="$HOME/.local/state/home-manager/gcroots/current-home/home-path/Applications"

    # Remove old aliases to prevent duplicates
    $DRY_RUN_CMD find "$appsDir" -maxdepth 1 -type f -name "*.app" -delete 2>/dev/null || true

    # Create new aliases using mkalias for proper macOS app linking
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

  # macOS-specific session variables
  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";
  };
}
