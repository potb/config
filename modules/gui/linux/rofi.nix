{
  pkgs,
  lib,
  inputs,
  ...
}: {
  home.linux = {
    pkgs,
    lib,
    inputs,
    ...
  }: {
    programs.rofi.enable = true;

    systemd.user.services.awww-daemon = {
      Unit = {
        Description = "awww wallpaper daemon";
        PartOf = ["graphical-session.target"];
        After = ["graphical-session.target"];
      };
      Service = {
        ExecStart = "${pkgs.awww}/bin/awww-daemon";
        Restart = "on-failure";
        RestartSec = 5;
      };
    };

    systemd.user.services.update-nasa-apod-wallpaper = let
      curl = "${pkgs.curl}/bin/curl";
      grep = "${pkgs.gnugrep}/bin/grep";
      sed = "${pkgs.gnused}/bin/sed";
      awww = "${pkgs.awww}/bin/awww";
      hyprctl = "${
        inputs.hy3.inputs.hyprland.packages.${pkgs.stdenv.hostPlatform.system}.hyprland
      }/bin/hyprctl";
      magick = "${pkgs.imagemagick}/bin/magick";
      jq = "${pkgs.jq}/bin/jq";
      script = pkgs.writeShellScript "update-nasa-apod-wallpaper" ''
        set -eu

        IMAGE_DIR="$HOME/Pictures/nasa-apod"
        IMAGE_PATH="$IMAGE_DIR/apod.jpg"
        TEMP_IMAGE_PATH="$IMAGE_DIR/apod_temp.jpg"
        APOD_URL="https://apod.nasa.gov/apod/astropix.html"
        APOD_BASE="https://apod.nasa.gov/apod/"
        BAR_HEIGHT=0

        mkdir -p "$IMAGE_DIR"

        echo "Fetching NASA Astronomy Picture of the Day..."

        RETRY_COUNT=0
        MAX_RETRIES=3
        SUCCESS=false

        while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
          if PAGE_CONTENT=$(${curl} -sL --max-time 15 "$APOD_URL"); then
            IMAGE_REL=$(echo "$PAGE_CONTENT" | ${grep} -oP 'href="image/[^"]+' | head -1 | ${sed} 's/href="//')
            if [ -n "$IMAGE_REL" ]; then
              SUCCESS=true
            else
              echo "No image found on page, retrying..."
              RETRY_COUNT=$((RETRY_COUNT + 1))
              sleep 5
            fi
          else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
              echo "Page fetch failed, retrying in 5 seconds... ($RETRY_COUNT/$MAX_RETRIES)"
              sleep 5
            fi
          fi
        done

        if [ "$SUCCESS" = "false" ]; then
          echo "Failed to fetch APOD page after $MAX_RETRIES attempts. Keeping existing wallpaper."
          exit 0
        fi

        IMAGE_URL="$APOD_BASE$IMAGE_REL"
        echo "Image URL: $IMAGE_URL"

        TITLE=$(echo "$PAGE_CONTENT" | ${grep} -oP '(?<=<b>)[^<]+' | head -1 || echo "Unknown")
        echo "Title: $TITLE"

        echo "Downloading image..."

        RETRY_COUNT=0
        SUCCESS=false

        while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
          if ${curl} -sL --max-time 60 "$IMAGE_URL" -o "$TEMP_IMAGE_PATH"; then
            SUCCESS=true
          else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
              echo "Image download failed, retrying in 5 seconds... ($RETRY_COUNT/$MAX_RETRIES)"
              sleep 5
            fi
          fi
        done

        if [ "$SUCCESS" = "false" ]; then
          echo "Failed to download image after $MAX_RETRIES attempts. Keeping existing wallpaper."
          rm -f "$TEMP_IMAGE_PATH"
          exit 0
        fi

        if [ ! -s "$TEMP_IMAGE_PATH" ] || [ "$(wc -c < "$TEMP_IMAGE_PATH")" -lt 1000 ]; then
          echo "Downloaded file is empty or too small. Keeping existing wallpaper."
          rm -f "$TEMP_IMAGE_PATH"
          exit 0
        fi

        mv "$TEMP_IMAGE_PATH" "$IMAGE_PATH"
        echo "Wallpaper updated successfully: $TITLE"

        # Process wallpaper for each monitor, accounting for bar height
        MONITORS=$(${hyprctl} monitors -j 2>/dev/null || echo "[]")
        if [ "$MONITORS" = "[]" ]; then
          echo "No monitors detected, skipping wallpaper set."
          exit 0
        fi

        echo "$MONITORS" | ${jq} -r '.[] | "\(.name) \(.width) \(.height)"' | while read -r MON_NAME MON_W MON_H; do
          VISIBLE_H=$((MON_H - BAR_HEIGHT))
          echo "Processing for $MON_NAME: ''${MON_W}x''${MON_H}, visible area ''${MON_W}x''${VISIBLE_H}"

          PROCESSED_MON="$IMAGE_DIR/apod_processed_$MON_NAME.png"

          # Create black canvas at full monitor resolution, fit image into visible area, center in top portion
          ${magick} "$IMAGE_PATH" \
            -resize "''${MON_W}x''${VISIBLE_H}" \
            -background black \
            -gravity north \
            -extent "''${MON_W}x''${MON_H}" \
            "$PROCESSED_MON"

          echo "Setting wallpaper on $MON_NAME..."
          ${awww} img -o "$MON_NAME" "$PROCESSED_MON" --transition-type fade --transition-duration 2 || echo "awww failed for $MON_NAME"
        done
      '';
    in {
      Unit = {
        Description = "Update NASA Astronomy Picture of the Day Wallpaper";
        After = [
          "awww-daemon.service"
          "network-online.target"
        ];
        Requires = ["awww-daemon.service"];
        Wants = ["network-online.target"];
      };
      Service = {
        Type = "oneshot";
        ExecStart = "${script}";
      };
    };

    systemd.user.timers.update-nasa-apod-wallpaper = {
      Unit.Description = "Update NASA APOD wallpaper hourly";
      Timer = {
        OnCalendar = "hourly";
        OnStartupSec = "2min";
        Persistent = true;
        Unit = "update-nasa-apod-wallpaper.service";
      };
      Install.WantedBy = ["timers.target"];
    };
  };
}
