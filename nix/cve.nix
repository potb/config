{
  pkgs,
  lib ? pkgs.lib,
  grypeDbIndex ? ./grype-db.json,
}: let
  index = builtins.fromJSON (builtins.readFile grypeDbIndex);

  grypeDb = pkgs.fetchurl {
    name = "grype-db-${index.schemaVersion}.tar.zst";
    url = "https://grype.anchore.io/databases/v6/${index.path}";
    sha256 = lib.removePrefix "sha256:" index.checksum;
  };

  dependencyAttrs = [
    "buildInputs"
    "propagatedBuildInputs"
    "nativeBuildInputs"
    "propagatedNativeBuildInputs"
    "depsBuildBuild"
    "depsBuildBuildPropagated"
    "depsBuildTarget"
    "depsBuildTargetPropagated"
    "depsHostHost"
    "depsHostHostPropagated"
    "depsTargetTarget"
    "depsTargetTargetPropagated"
  ];

  attempt = fallback: value: let
    result = builtins.tryEval (builtins.deepSeq value value);
  in
    if result.success
    then result.value
    else fallback;

  attemptShallow = fallback: value: let
    result = builtins.tryEval value;
  in
    if result.success
    then result.value
    else fallback;

  pathOf = drv: attempt null (builtins.unsafeDiscardStringContext drv.outPath);

  isDerivationSafely = value: attemptShallow false (lib.isDerivation value);

  flattenSafely = value: let
    forced = attemptShallow [] value;
  in
    if builtins.isList forced
    then lib.concatMap flattenSafely forced
    else [forced];

  derivationsIn = value: builtins.filter isDerivationSafely (flattenSafely value);

  dependenciesOf = drv:
    lib.concatMap (attr: derivationsIn (drv.${attr} or [])) dependencyAttrs
    ++ derivationsIn (drv.stdenv or []);

  node = drv: {
    key = pathOf drv;
    inherit drv;
  };

  nodesFrom = roots:
    builtins.genericClosure {
      startSet = builtins.filter (n: n.key != null) (map node (derivationsIn roots));
      operator = n: builtins.filter (m: m.key != null) (map node (dependenciesOf n.drv));
    };

  patchName = patch:
    attempt null (builtins.unsafeDiscardStringContext (
      if isDerivationSafely patch
      then patch.name
      else baseNameOf (toString patch)
    ));

  describe = drv: let
    parsed = builtins.parseDrvName (drv.name or "");
  in {
    outputs = builtins.filter (p: p != null) (map (o: attempt null (pathOf drv.${o})) (attempt ["out"] (drv.outputs or ["out"])));
    name = attempt parsed.name (builtins.unsafeDiscardStringContext (drv.pname or parsed.name));
    version = attempt parsed.version (builtins.unsafeDiscardStringContext (drv.version or parsed.version));
    cpe = attempt null (drv.meta.identifiers.cpe or null);
    patches = builtins.filter (p: p != null) (map patchName (flattenSafely (drv.patches or [])));
  };

  rootsOf = config:
    flattenSafely (config.environment.systemPackages or [])
    ++ flattenSafely (config.fonts.packages or [])
    ++ flattenSafely (attemptShallow [] (config.nix.package or []))
    ++ lib.concatMap (user: flattenSafely (user.home.packages or []))
    (builtins.attrValues (attemptShallow {} (config.home-manager.users or {})));

  reportFor = name: toplevel: roots: let
    table = pkgs.writeText "cve-${name}-packages.json" (builtins.toJSON (map (n: describe n.drv) (nodesFrom roots)));
    closure = pkgs.closureInfo {rootPaths = [toplevel];};
  in
    pkgs.runCommand "cve-${name}"
    {
      nativeBuildInputs = [pkgs.grype pkgs.python3];
    }
    ''
      mkdir -p $out
      ln -s ${grypeDb} $out/grype-db.tar.zst
      export HOME=$TMPDIR
      export GRYPE_DB_CACHE_DIR=$TMPDIR/grype-db
      export GRYPE_DB_AUTO_UPDATE=false
      export GRYPE_DB_VALIDATE_AGE=false
      export GRYPE_CHECK_FOR_APP_UPDATE=false
      export NO_COLOR=1

      python3 ${./cve-sbom.py} bom ${table} ${closure}/store-paths ${lib.escapeShellArg name} $out > sbom-summary.txt

      grype db import ${grypeDb}
      grype sbom:$out/bom.cdx.json --add-cpes-if-none -o json=$out/grype.json -o table=$out/report.txt

      {
        echo "host: ${name}"
        echo "grype db: ${index.path} (built ${index.built})"
        cat sbom-summary.txt
        python3 ${./cve-sbom.py} summary $out
      } > $out/summary.txt
      cat $out/summary.txt
    '';

  forHost = name: host: reportFor name host.config.system.build.toplevel (rootsOf host.config);
in {
  inherit grypeDb reportFor forHost;
}
