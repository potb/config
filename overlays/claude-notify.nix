final: prev: {
  claude-notify = prev.stdenv.mkDerivation {
    pname = "claude-notify";
    version = "1.0.0";

    src = prev.fetchFromGitHub {
      owner = "mylee04";
      repo = "claude-notify";
      rev = "2e56660884474f08ce6ce11a39276ec74e21bcf1";
      sha256 = "sha256-TcGJkXgBOe8xVPo+2GxvczOakadM4SbWf+DUbTB4kzg=";
    };

    buildInputs = [prev.jq] ++ prev.lib.optionals prev.stdenv.isDarwin [prev.terminal-notifier];

    nativeBuildInputs = [
      prev.makeWrapper
    ];

    dontBuild = true;

    installPhase = ''
      runHook preInstall

      # Install library files
      mkdir -p $out/lib/claude-notify
      cp -r lib/claude-notify/* $out/lib/claude-notify/

      # Install main binary
      mkdir -p $out/bin
      cp bin/claude-notify $out/bin/claude-notify
      chmod +x $out/bin/claude-notify

      # Update library path in main script
      substituteInPlace $out/bin/claude-notify \
        --replace 'LIB_DIR="$HOME/.claude-notify/lib/claude-notify"' \
                  'LIB_DIR="'$out'/lib/claude-notify"'

      # Create symlinks for cn and cnp
      ln -s $out/bin/claude-notify $out/bin/cn
      ln -s $out/bin/claude-notify $out/bin/cnp

      # Wrap with dependencies
      wrapProgram $out/bin/claude-notify \
        --prefix PATH : ${
        prev.lib.makeBinPath (
          [prev.jq] ++ prev.lib.optionals prev.stdenv.isDarwin [prev.terminal-notifier]
        )
      }

      # Install shell completions
      mkdir -p $out/share/bash-completion/completions
      mkdir -p $out/share/zsh/site-functions
      cp completions/bash/claude-notify $out/share/bash-completion/completions/
      cp completions/zsh/_claude-notify $out/share/zsh/site-functions/

      runHook postInstall
    '';

    meta = with prev.lib; {
      description = "CLI notification tool for Claude Code";
      homepage = "https://github.com/potb/claude-notify";
      license = licenses.mit;
      platforms = platforms.darwin ++ platforms.linux;
    };
  };
}
