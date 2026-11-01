{lib, ...}: final: prev: let
  staleVersion = "0.56.0.1";
  currentVersion = prev.hyprlandPlugins.hy3.version;
in {
  hyprlandPlugins =
    prev.hyprlandPlugins
    // {
      hy3 =
        lib.throwIf (currentVersion != staleVersion)
        ''
          overlays/hy3.nix builds hy3 from the upstream hl0.57.0 tag because nixpkgs
          shipped Hyprland 0.57.0 with hy3 ${staleVersion}, which does not compile against it.
          nixpkgs now ships hy3 ${currentVersion}, so delete overlays/hy3.nix.
        ''
        (prev.hyprlandPlugins.hy3.overrideAttrs (_: {
          version = "0.57.0";
          src = final.fetchFromGitHub {
            owner = "outfoxxed";
            repo = "hy3";
            tag = "hl0.57.0";
            hash = "sha256-9qAw3Xsa0xN9b5ERiWEGL1fBq37GLskcrBj/6ax8PU4=";
          };
        }));
    };
}
