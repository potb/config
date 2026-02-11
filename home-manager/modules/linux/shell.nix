{lib, ...}: {
  programs.zsh.initContent = lib.mkAfter ''
    unalias l
  '';
}
