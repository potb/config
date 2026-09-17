{
  lib,
  pkgs,
  platform,
  requests,
}: let
  catalog = import ./catalog.nix {inherit lib pkgs;};

  platformKey =
    if platform == "nixos"
    then "linux"
    else "darwin";

  known = name: catalog ? ${name};

  recipesFor = name: catalog.${name}.channels;

  defaultChannel = name: catalog.${name}.defaultChannel.${platformKey} or "nixpkgs";

  selected =
    lib.mapAttrs (
      name: request:
        if builtins.isString request
        then request
        else if request
        then defaultChannel name
        else "none"
    )
    requests;

  unknown = builtins.filter (name: !known name) (builtins.attrNames selected);

  unavailable =
    builtins.filter (
      name:
        known name
        && selected.${name} != "none"
        && !(recipesFor name ? ${selected.${name}})
    )
    (builtins.attrNames selected);

  describe = name: let
    channels = builtins.attrNames (recipesFor name) ++ ["none"];
  in "${name}: no \"${selected.${name}}\" channel; this package offers ${lib.concatStringsSep ", " channels}";

  failures =
    map (name: "${name}: not in modules/lib/catalog.nix") unknown
    ++ map describe unavailable;

  chosen =
    lib.filterAttrs (
      name: channel: known name && channel != "none" && recipesFor name ? ${channel}
    )
    selected;

  fragments = lib.mapAttrsToList (name: channel: (recipesFor name).${channel}) chosen;

  merge = key:
    lib.mkMerge (
      map (fragment: fragment.${key} or {}) fragments
    );

  availabilityAssertions =
    lib.mapAttrsToList (name: channel: {
      assertion = (recipesFor name).${channel}.available or true;
      message = "potb packages: ${name} via ${channel} has no build for ${pkgs.stdenv.hostPlatform.system}; choose another channel or \"none\" for this host";
    })
    chosen;
in
  if failures != []
  then
    throw ''
      package channel selection failed:
        ${lib.concatStringsSep "\n  " failures}
    ''
  else {
    inherit availabilityAssertions;
    nixos = merge "nixos";
    darwin = merge "darwin";
    home = merge "home";
  }
