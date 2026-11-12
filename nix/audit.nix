{
  pkgs,
  lib ? pkgs.lib,
}: let
  defaults = {
    forbiddenPatterns = [
      "(^|[^[:alnum:]_.-])/build/"
      "/nix/var/nix/builds/"
      "/tmp/nix-build-"
      "/homeless-shelter"
    ];

    secretsMaxFileMB = 50;

    forbiddenClosureRefs = [
      "-gcc-[0-9.]+$"
      "-gcc-wrapper-"
      "-clang-[0-9.]+$"
      "-binutils-[0-9.]+$"
      "-cmake-[0-9.]+$"
      "-stdenv-"
    ];

    maxClosureMB = 1024;
    symlinks = true;
    elf = true;
    secrets = true;
  };

  nonRuntimeOutputs = ["dev" "devdoc" "doc" "man" "info"];

  allOutputs = drv: map (o: drv.${o}) (drv.outputs or ["out"]);

  auditOne = name: drv: let
    cfg = defaults // (drv.audit or {});
    outs = allOutputs drv;
    runtimeOuts =
      builtins.filter
      (o: !(builtins.elem (o.outputName or "out") nonRuntimeOutputs))
      outs;
    closure = pkgs.closureInfo {rootPaths = runtimeOuts;};
    on = b:
      if b
      then "1"
      else "";
  in
    pkgs.runCommand "audit-${name}"
    {
      nativeBuildInputs = with pkgs; [coreutils findutils gnugrep patchelf gitleaks];
      outPaths = outs;
    }
    ''
      set -euo pipefail
      fail=0
      flag() { echo "  FAIL [$1] $2"; fail=1; }

      forbidden=( ${lib.escapeShellArgs cfg.forbiddenPatterns} )
      closureRefs=( ${lib.escapeShellArgs cfg.forbiddenClosureRefs} )

      for p in $outPaths; do
        echo "== auditing $p"

        if [ -n "${on cfg.symlinks}" ]; then
          while IFS= read -r -d "" l; do
            flag dangling-symlink "$l -> $(readlink "$l")"
          done < <(find "$p" -xtype l -print0)
        fi

        for s in "''${forbidden[@]}"; do
          while IFS= read -r f; do
            flag impure-path "$f matches /$s/"
          done < <(grep -rlaE -- "$s" "$p" || true)
        done

        if [ -n "${on cfg.elf}" ]; then
          while IFS= read -r -d "" f; do
            [ "$(head -c4 "$f" | od -An -c | tr -d ' \n')" = '177ELF' ] || continue
            interp=$(patchelf --print-interpreter "$f" 2>/dev/null || true)
            if [ -n "$interp" ] && [[ "$interp" != /nix/store/* ]]; then
              flag elf-interp "$f uses interpreter $interp"
            fi
            rpath=$(patchelf --print-rpath "$f" 2>/dev/null || true)
            IFS=: read -ra parts <<< "$rpath"
            for r in "''${parts[@]}"; do
              case "$r" in
                /nix/store/*|'$ORIGIN'*|"") ;;
                *) flag elf-rpath "$f has RPATH entry $r" ;;
              esac
            done
          done < <(find "$p" -type f -print0)
        fi

        if [ -n "${on cfg.secrets}" ]; then
          if ! gitleaks dir "$p" --no-banner --redact --log-level warn \
                 --max-target-megabytes ${toString cfg.secretsMaxFileMB}; then
            flag secrets "gitleaks reported potential secrets in $p"
          fi
        fi
      done

      echo "== runtime closure"
      size=$(cat ${closure}/total-nar-size)
      max=$(( ${toString cfg.maxClosureMB} * 1024 * 1024 ))
      echo "  $(( size / 1024 / 1024 )) MiB across $(wc -l < ${closure}/store-paths) store paths"
      [ "$size" -le "$max" ] || flag closure-size "$(( size / 1024 / 1024 )) MiB > ${toString cfg.maxClosureMB} MiB"

      for re in "''${closureRefs[@]}"; do
        while IFS= read -r sp; do
          flag closure-ref "$sp matches /$re/"
        done < <(grep -E -- "$re" ${closure}/store-paths || true)
      done

      if [ "$fail" -ne 0 ]; then
        echo "audit FAILED for ${name}"
        exit 1
      fi
      echo "audit passed for ${name}" > $out
    '';
in {
  inherit auditOne defaults;

  forPackages = packages:
    lib.mapAttrs'
    (n: d: lib.nameValuePair "audit-${n}" (auditOne n d))
    (lib.filterAttrs (_: lib.isDerivation) packages);
}
