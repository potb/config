{inputs, ...}: {
  nixos = {};

  darwin = {};

  home = {pkgs, ...}: {
    home.packages = [inputs.llm-agents.packages.${pkgs.stdenv.hostPlatform.system}.grok-bot];
  };
}
