{pkgs, ...}: let
  service-name = "update-apod-wallpaper";
in {
  systemd.services.${service-name} = {
    description = "Update APOD Wallpaper";
    enableStrictShellChecks = true;
    script = let
      curl = "${pkgs.curl}/bin/curl";
      feh = "${pkgs.feh}/bin/feh";
      file = "${pkgs.file}/bin/file";
    in ''
      set -eu

      IMAGE_DIR="$HOME/Pictures/apod"
      IMAGE_PATH="$IMAGE_DIR/apod.jpg"
      TEMP_IMAGE_PATH="$IMAGE_DIR/apod_temp.jpg"
      APOD_URL="https://apod.nasa.gov/apod/astropix.html"

      export DISPLAY=:0

      mkdir -p "$IMAGE_DIR"

      IMAGE_URL=$(${curl} -s $APOD_URL | grep -oP '(?<=<a href="image/).*?(?=")' | head -n 1 || echo "")
      if [ -z "$IMAGE_URL" ]; then
        echo "No image found on APOD page."
        exit 1
      fi

      IMAGE_URL="https://apod.nasa.gov/apod/image/$IMAGE_URL"

      ${curl} -s "$IMAGE_URL" -o "$TEMP_IMAGE_PATH"

      if ${file} "$TEMP_IMAGE_PATH" | grep -qE 'image|bitmap'; then
        mv "$TEMP_IMAGE_PATH" "$IMAGE_PATH"
        ${feh} --bg-max "$IMAGE_PATH"
      else
        echo "Downloaded file is not a valid image. Keeping the old wallpaper."
        rm "$TEMP_IMAGE_PATH"
      fi
    '';
    serviceConfig = {
      Type = "oneshot";
      User = "potb";
      Environment = "DISPLAY=:0";
    };
    wantedBy = ["multi-user.target"];
    wants = ["network-online.target"];
  };

  systemd.timers.${service-name} = {
    wantedBy = ["timers.target"];
    timerConfig = {
      OnCalendar = "0/1:00:00"; # Run every 6 hours
      Persistent = true;
      Unit = "${service-name}.service";
    };
  };
}
