{
  lib,
  python3Packages,
  src,
  version,
}: let
  apscheduler4 = python3Packages.buildPythonPackage rec {
    pname = "apscheduler";
    version = "4.0.0a6";
    pyproject = true;

    src = python3Packages.fetchPypi {
      inherit pname version;
      hash = "sha256-UTRhfAKPCX3koJq77vxCYlywzjrctM5J10zCYFQIR2E=";
    };

    build-system = [python3Packages.setuptools python3Packages.setuptools-scm];

    dependencies = with python3Packages; [
      anyio
      attrs
      tenacity
      tzlocal
    ];

    doCheck = false;

    pythonImportsCheck = ["apscheduler"];

    meta = {
      description = "Task scheduling library for Python";
      homepage = "https://github.com/agronholm/apscheduler";
      license = lib.licenses.mit;
    };
  };
in
  python3Packages.buildPythonApplication {
    pname = "tsm-app";
    inherit src version;
    pyproject = true;

    env.SETUPTOOLS_SCM_PRETEND_VERSION = version;
    env.HATCH_VCS_PRETEND_VERSION = version;

    build-system = with python3Packages; [
      hatchling
      hatch-vcs
    ];

    dependencies =
      [apscheduler4]
      ++ (with python3Packages; [
        pyside6
        aiohttp
        pydantic
        typing-extensions
        aiosqlite
        keyring
        structlog
        tomli-w
        pyyaml
      ]);

    nativeCheckInputs = with python3Packages; [
      pytestCheckHook
      pytest-asyncio
      aioresponses
    ];

    preCheck = ''
      export QT_QPA_PLATFORM=offscreen
      export HOME=$(mktemp -d)
    '';

    postCheck = ''
      python ${./import_all.py}
    '';

    dontWrapQtApps = true;

    pythonImportsCheck = ["tsm"];

    meta = {
      description = "TradeSkillMaster Desktop App for Linux, downloads WoW auction data and writes AppData.lua for the TSM addon";
      homepage = "https://github.com/exceptionptr/tsm-app-linux";
      license = lib.licenses.mit;
      mainProgram = "tsm-app";
      platforms = lib.platforms.linux;
    };
  }
