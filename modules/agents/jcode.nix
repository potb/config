{
  inputs,
  lib,
  ...
}: {
  nixos = {};

  darwin = {};

  home = {
    config,
    lib,
    pkgs,
    ...
  }: let
    # Seeded, not managed: home.file would install read-only store symlinks, and
    # these files are edited live. Copy an edit back into this repo to persist it.
    #
    # ./jcode is mirrored into ~/.jcode wholesale rather than listed file by
    # file, so adding a skill means dropping jcode/skills/<name>/SKILL.md into
    # the tree with no change to this module. listFilesRecursive yields only
    # regular files, so nested layouts need no extra handling here, and the
    # seed function below already creates missing parent directories.
    #
    # Two consequences of walking a directory instead of naming files. A new
    # file must be git-added before it is visible: a flake copies only tracked
    # files into the store, so an untracked skill evaluates away silently
    # rather than failing (verified, and it is also why .DS_Store cannot leak
    # in, being gitignored). And deleting a file here does not delete the
    # seeded copy, since the walk can only enumerate what exists; remove
    # ~/.jcode/skills/<name> by hand when retiring a skill.
    seedRoot = ./jcode;

    linuxMcpServers = {
      computer-use = {
        command = "/etc/profiles/per-user/potb/bin/computer-use-linux";
        args = ["mcp"];
        env.YDOTOOL_SOCKET = "/run/ydotoold/socket";
      };
    };

    sharedMcp = lib.importJSON (seedRoot + "/mcp.json");

    mcpJson = pkgs.writeText "mcp.json" (builtins.toJSON (
      if pkgs.stdenv.hostPlatform.isLinux
      then sharedMcp // {mcpServers = sharedMcp.mcpServers // linuxMcpServers;}
      else sharedMcp
    ));

    seedFiles =
      lib.listToAttrs (map (path: let
        rel = lib.removePrefix "${toString seedRoot}/" (toString path);
      in
        lib.nameValuePair ".jcode/${rel}" path)
      (lib.filesystem.listFilesRecursive seedRoot))
      // {".jcode/mcp.json" = mcpJson;};

    # Hooks are spawned by jcode as programs rather than sourced, so they need
    # the exec bit the default 0644 seed mode would strip.
    seedMode = rel:
      if lib.hasPrefix ".jcode/hooks/" rel
      then "0755"
      else "0644";

    seedScript = lib.concatStringsSep "\n" (lib.mapAttrsToList (rel: src: ''
        seed_jcode_file ${lib.escapeShellArg rel} ${lib.escapeShellArg "${src}"} ${seedMode rel}
      '')
      seedFiles);
  in {
    # Overwrites only while the target still matches what was seeded last time.
    # Once edited, the live file wins and the nix version lands in <file>.nix-new.
    home.packages = [pkgs.jcode];

    sops = {
      defaultSopsFile = ../../secrets/jcode.yaml;
      age.sshKeyPaths = ["${config.home.homeDirectory}/.ssh/id_ed25519"];
      secrets.exa-api-key = {};
    };

    home.activation.seedJcodeFiles = lib.hm.dag.entryAfter ["writeBoundary"] ''
      seed_jcode_file() {
        dest="$HOME/$1"
        src="$2"
        mode="$3"
        stamp="$(dirname "$dest")/.$(basename "$dest").nix-seeded"

        $DRY_RUN_CMD mkdir -p "$(dirname "$dest")"

        # -L catches a store symlink left by an earlier home.file generation.
        if [ ! -e "$dest" ] || [ -L "$dest" ] \
          || ${pkgs.diffutils}/bin/cmp -s "$dest" "$stamp"; then
          $DRY_RUN_CMD rm -f "$dest"
          $DRY_RUN_CMD install -m "$mode" "$src" "$dest"
          $DRY_RUN_CMD install -m 0644 "$src" "$stamp"
        elif ${pkgs.diffutils}/bin/cmp -s "$dest" "$src"; then
          $DRY_RUN_CMD install -m 0644 "$src" "$stamp"
        else
          $DRY_RUN_CMD install -m 0644 "$src" "$dest.nix-new"
          echo "jcode: kept live edits in $dest (nix version at $dest.nix-new)"
        fi
      }

      ${seedScript}
    '';

    # jcode rewrites config.toml at runtime, so it must be a real file owned by
    # the user rather than a read-only store symlink. Unlike the seed tree
    # above, the repo copy always wins: it is reinstalled on every switch.
    # Runtime changes that differ are kept once in config.toml.bak, so copy
    # anything worth keeping back into modules/agents/config.toml.
    home.activation.jcodeConfig = lib.hm.dag.entryAfter ["writeBoundary"] ''
      dest="$HOME/.jcode/config.toml"
      run mkdir -p "$HOME/.jcode"
      if [ -f "$dest" ] && [ ! -L "$dest" ] \
        && ! ${pkgs.diffutils}/bin/cmp -s "$dest" ${./config.toml}; then
        run cp -f "$dest" "$dest.bak"
      fi
      run rm -f "$dest"
      run install -m 0644 ${./config.toml} "$dest"
    '';

    home.sessionVariables = {
      JCODE_CHECK_UPDATES = "false";
      JCODE_NO_AUTO_UPDATE = "1";
      JCODE_NO_MACOS_OPTION_CHAR_SHORTCUTS = "1";
    };
  };
}
