{pkgs, ...}: let
  user = "potb";
  credFile = "/var/lib/keyring-unlock/${user}.cred";
  secretDir = "/run/keyring-unlock";
  secretFile = "${secretDir}/${user}";

  # One-time setup helper: seals the login keyring password to the TPM so the
  # boot-time service can recover it without a human present.
  sealScript = pkgs.writeShellScriptBin "keyring-seal-password" ''
    set -euo pipefail
    if [ "$(id -u)" -ne 0 ]; then
      echo "run as root (sudo keyring-seal-password)" >&2
      exit 1
    fi
    mkdir -p "$(dirname ${credFile})"
    chmod 0700 "$(dirname ${credFile})"
    printf 'Login keyring password for ${user}: ' >&2
    read -rs password
    echo >&2
    printf '%s' "$password" \
      | ${pkgs.systemd}/bin/systemd-creds encrypt --with-key=tpm2 --name=keyring - ${credFile}
    chmod 0600 ${credFile}
    echo "sealed to ${credFile}" >&2
  '';
in {
  environment.systemPackages = [sealScript];

  # Root side: decrypt the TPM-sealed password into tmpfs, readable only by the
  # user, so the unprivileged session service can feed it to gnome-keyring.
  systemd.services.keyring-secret = {
    description = "Provide TPM-sealed keyring password for ${user}";
    wantedBy = ["multi-user.target"];
    unitConfig.ConditionPathExists = credFile;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      LoadCredentialEncrypted = "keyring:${credFile}";
      RuntimeDirectory = "keyring-unlock";
      RuntimeDirectoryMode = "0755";
      ExecStart = pkgs.writeShellScript "keyring-secret-install" ''
        set -euo pipefail
        install -m 0400 -o ${user} "$CREDENTIALS_DIRECTORY/keyring" ${secretFile}
      '';
    };
  };

  # Session side: unlock the keyring as soon as the graphical session exists.
  systemd.user.services.keyring-unlock = {
    description = "Unlock the GNOME keyring without a prompt";
    wantedBy = ["graphical-session.target"];
    after = ["graphical-session.target"];
    partOf = ["graphical-session.target"];
    unitConfig.ConditionPathExists = secretFile;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = pkgs.writeShellScript "keyring-unlock" ''
        set -euo pipefail
        ${pkgs.coreutils}/bin/cat ${secretFile} \
          | ${pkgs.gnome-keyring}/bin/gnome-keyring-daemon --unlock >/dev/null
      '';
    };
  };
}
