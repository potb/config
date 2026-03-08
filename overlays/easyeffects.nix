{...}: final: prev: {
  easyeffects = prev.easyeffects.overrideAttrs (old: {
    patches =
      (old.patches or [])
      ++ [
        ./easyeffects-save-crash.patch
      ];
  });
}
