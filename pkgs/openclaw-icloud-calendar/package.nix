{
  lib,
  stdenvNoCC,
  fetchurl,
  esbuild,
  jq,
  src,
  openclawGateway,
}: let
  typebox = fetchurl {
    url = "https://registry.npmjs.org/@sinclair/typebox/-/typebox-0.34.49.tgz";
    hash = "sha512-brySQQs7Jtn0joV8Xh9ZV/hZb9Ozb0pmazDIASBkYKCjXrXU3mpcFahmK/z4YDhGkQvP9mWJbVyahdtU5wQA+A==";
  };
  manifest = lib.importJSON (src + "/openclaw.plugin.json");
in
  stdenvNoCC.mkDerivation {
    pname = "openclaw-icloud-calendar";
    inherit (manifest) version;
    inherit src;

    nativeBuildInputs = [esbuild jq];

    buildPhase = ''
      runHook preBuild
      mkdir -p node_modules/@sinclair/typebox
      tar -xzf ${typebox} -C node_modules/@sinclair/typebox --strip-components=1
      esbuild src/index.ts --bundle --platform=node --format=esm --target=node22 \
        --external:openclaw --external:'openclaw/*' --outfile=dist/index.js
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      mkdir -p $out/node_modules
      cp -r dist skills openclaw.plugin.json README.md LICENSE $out/
      jq 'del(.devDependencies, .dependencies, .scripts)
        | .openclaw.extensions = ["./dist/index.js"]' package.json > $out/package.json
      ln -s ${openclawGateway}/lib/openclaw $out/node_modules/openclaw
      runHook postInstall
    '';

    meta = {
      description = "OpenClaw plugin for Apple iCloud Calendar over CalDAV";
      homepage = "https://github.com/omarshahine/openclaw-icloud-calendar";
      license = lib.licenses.mit;
      platforms = lib.platforms.linux;
    };
  }
