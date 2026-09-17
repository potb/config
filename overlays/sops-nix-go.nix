{lib, ...}: final: prev: let
  removedBuilder = "buildGo125Module";
  replacementBuilder = "buildGo126Module";
  stillNeeded = builtins.tryEval (prev.${removedBuilder} {
    pname = "sops-nix-go-builder-probe";
    version = "0";
    src = null;
    vendorHash = null;
  });
in {
  ${removedBuilder} =
    lib.throwIf (stillNeeded.success)
    ''
      overlays/sops-nix-go.nix redirects ${removedBuilder} to ${replacementBuilder} because
      nixpkgs removed the Go 1.25 builder while sops-nix still calls it in
      pkgs/sops-install-secrets/default.nix.

      ${removedBuilder} now evaluates on its own, so nixpkgs has brought it back or
      sops-nix no longer needs the redirect.

      Re-check https://github.com/Mic92/sops-nix/blob/master/pkgs/sops-install-secrets/default.nix
      and delete this overlay once sops-nix targets a builder that nixpkgs ships.
    ''
    prev.${replacementBuilder};
}
