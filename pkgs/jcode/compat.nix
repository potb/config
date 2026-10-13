{
  lib,
  src,
  desktopSrc,
}: let
  workflow = builtins.readFile (desktopSrc + "/.github/workflows/cross-platform-release.yml");

  pinMatch = builtins.match ".*repository: 1jehuang/jcode\n[[:space:]]+ref: ([0-9a-f]{40}).*" workflow;

  desktopPin =
    if pinMatch == null
    then throw "pkgs/jcode: no jcode ref found after `repository: 1jehuang/jcode` in jcode-desktop's cross-platform-release.yml. See docs/jcode-desktop.md."
    else builtins.head pinMatch;

  jcodeRev = src.rev or (throw "pkgs/jcode: the jcode input has no rev, so its pin cannot be compared with jcode-desktop's.");

  desktopManifests =
    [(desktopSrc + "/Cargo.toml")]
    ++ map (member: desktopSrc + "/${member}/Cargo.toml")
    (lib.remove "." (lib.importTOML (desktopSrc + "/Cargo.toml")).workspace.members);

  pathDepsOf = manifest: let
    toml = lib.importTOML manifest;
    tables =
      [(toml.dependencies or {}) (toml.build-dependencies or {}) (toml.dev-dependencies or {})]
      ++ lib.mapAttrsToList (_: target: target.dependencies or {}) (toml.target or {});
  in
    lib.concatMap (table:
      lib.mapAttrsToList (_: spec: spec.path or null) (lib.filterAttrs (_: spec: builtins.isAttrs spec) table))
    tables;

  jcodeCrates = lib.unique (lib.concatMap (manifest:
    lib.concatMap (path: let
      found = builtins.match ".*jcode/crates/([^/]+)" (toString path);
    in
      lib.optional (found != null) (builtins.head found))
    (lib.remove null (pathDepsOf manifest)))
  desktopManifests);

  missingCrates = builtins.filter (crate: !builtins.pathExists (src + "/crates/${crate}/Cargo.toml")) jcodeCrates;
in {
  inherit desktopPin jcodeRev jcodeCrates missingCrates;

  check =
    if jcodeRev != desktopPin
    then throw "pkgs/jcode: jcode is locked at ${jcodeRev}, but jcode-desktop ${desktopSrc.shortRev or ""} is released against jcode ${desktopPin}. Run scripts/update-jcode to move both inputs together. See docs/jcode-desktop.md."
    else if missingCrates != []
    then throw "pkgs/jcode: jcode-desktop links jcode crates that jcode ${jcodeRev} does not have: ${lib.concatStringsSep ", " missingCrates}. Run scripts/update-jcode to pick a jcode-desktop commit that builds against it. See docs/jcode-desktop.md."
    else true;
}
