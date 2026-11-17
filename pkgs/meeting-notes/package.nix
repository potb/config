{
  lib,
  python3Packages,
}: let
  root = ./.;
in
  python3Packages.buildPythonApplication {
    pname = "meeting-notes";
    version = "0.1.0";
    pyproject = true;

    src = lib.fileset.toSource {
      inherit root;
      fileset = lib.fileset.unions [
        (root + "/pyproject.toml")
        (root + "/meeting_notes")
        (root + "/tests")
        (root + "/pipe.md")
        (root + "/glossary.md")
      ];
    };

    build-system = [python3Packages.setuptools];

    nativeCheckInputs = [python3Packages.unittestCheckHook];
    unittestFlags = ["-s" "tests" "-t" "."];

    postInstall = ''
      install -Dm644 pipe.md glossary.md -t $out/share/meeting-notes
    '';

    meta = {
      description = "Records meetings and turns them into notes";
      license = lib.licenses.mit;
      platforms = lib.platforms.linux ++ lib.platforms.darwin;
      mainProgram = "meeting-notes";
    };
  }
