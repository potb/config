{
  pkgs,
  lib,
  ...
}: {
  # Workaround for home-manager bug #7352 on Darwin
  # Disable broken Darwin modules that pull in glibc
  home.file."Library/Fonts/.home-manager-fonts-version".enable = lib.mkForce false;
  home.file."Applications/Home Manager Apps".enable = lib.mkForce false;

  # Disable xresources (not used on macOS)
  stylix.targets.xresources.enable = false;

  # Link home-manager apps to Applications folder
  home.activation.linkHomeManagerApps = lib.hm.dag.entryAfter ["linkGeneration"] ''
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
}
