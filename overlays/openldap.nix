{lib, ...}: final: prev: let
  # Workaround for a flaky test in openldap-2.6.13 that breaks i686 (multilib)
  # builds: test017-syncreplication-refresh times out because the 7s sleep is
  # too short on slower 32-bit platforms.
  #
  # Tracking:
  #   https://github.com/NixOS/nixpkgs/issues/513245
  #   https://github.com/NixOS/nixpkgs/issues/426717
  #   https://github.com/NixOS/nixpkgs/pull/429119
  #   https://bugs.openldap.org/show_bug.cgi?id=10250
  #
  # Sentinel: this assertion fires the moment nixpkgs bumps openldap past
  # 2.6.13 (which is when the upstream fix is most likely to land — either via
  # a backport or in 2.6.14+). When that happens, re-check the issues above
  # and delete this overlay if the fix has shipped.
  brokenVersion = "2.6.13";
  currentVersion = prev.openldap.version;
in {
  openldap =
    lib.throwIf (currentVersion != brokenVersion)
    ''
      overlays/openldap.nix is pinned to openldap ${brokenVersion} but nixpkgs now ships ${currentVersion}.

      Re-check whether the i686 test-suite workaround is still required:
        https://github.com/NixOS/nixpkgs/issues/513245
        https://github.com/NixOS/nixpkgs/pull/429119

      If upstream has shipped the fix → delete overlays/openldap.nix.
      If not → bump `brokenVersion` in this file to ${currentVersion}.
    ''
    (prev.openldap.overrideAttrs (_: {
      doCheck = !prev.stdenv.hostPlatform.isi686;
    }));
}
