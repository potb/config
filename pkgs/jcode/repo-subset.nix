{lib}: root: {
  name,
  paths,
}: let
  rootString = toString root;

  keep = path: type: let
    relative = lib.removePrefix (rootString + "/") (toString path);
    isUnder = kept: lib.hasPrefix (kept + "/") (relative + "/");
    isAncestorOf = kept: lib.hasPrefix (relative + "/") (kept + "/");
    wanted = lib.any (kept: isUnder kept || isAncestorOf kept) paths;
    ignored = type == "directory" && (baseNameOf path == "target" || baseNameOf path == ".git");
  in
    wanted && !ignored;
in
  builtins.path {
    inherit name;
    path = root;
    filter = keep;
  }
