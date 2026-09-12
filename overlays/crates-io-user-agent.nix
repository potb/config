{lib, ...}: final: prev: let
  staticCrateUrl = {
    crateName,
    version,
  }: "https://static.crates.io/crates/${crateName}/${crateName}-${version}.crate";
in {
  fetchCrate = args @ {
    crateName ? args.pname or null,
    version,
    ...
  }:
    if crateName == null
    then prev.fetchCrate args
    else
      prev.fetchCrate (builtins.removeAttrs args ["url"]
        // {
          url = staticCrateUrl {inherit crateName version;};
        });
}
