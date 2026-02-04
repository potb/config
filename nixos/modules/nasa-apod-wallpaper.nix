{
  config,
  pkgs,
  ...
}: let
  service-name = "update-nasa-apod-wallpaper";
in {
  systemd.services.${service-name} = {
    description = "Update NASA Astronomy Picture of the Day Wallpaper";
    enableStrictShellChecks = true;
    script = let
      curl = "${pkgs.curl}/bin/curl";
      grep = "${pkgs.gnugrep}/bin/grep";
      sed = "${pkgs.gnused}/bin/sed";
      swww = "${pkgs.swww}/bin/swww";
    in ''
        set -eu

        IMAGE_DIR="$HOME/Pictures/nasa-apod"
        IMAGE_PATH="$IMAGE_DIR/apod.jpg"
        TEMP_IMAGE_PATH="$IMAGE_DIR/apod_temp.jpg"
        APOD_URL="https://apod.nasa.gov/apod/astropix.html"
        APOD_BASE="https://apod.nasa.gov/apod/"

        mkdir -p "$IMAGE_DIR"

        echo "Fetching NASA Astronomy Picture of the Day..."

        RETRY_COUNT=0
        MAX_RETRIES=3
        SUCCESS=false

        while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
          if PAGE_CONTENT=$(${curl} -sL --max-time 15 "$APOD_URL"); then
            # Extract image path from href="image/..." pattern
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

        # Extract title from page
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

        # Verify file exists and has content (>1KB to catch error pages)
        if [ ! -s "$TEMP_IMAGE_PATH" ] || [ "$(wc -c < "$TEMP_IMAGE_PATH")" -lt 1000 ]; then
          echo "Downloaded file is empty or too small. Keeping existing wallpaper."
          rm -f "$TEMP_IMAGE_PATH"
          exit 0
        fi

      # Update wallpaper
      mv "$TEMP_IMAGE_PATH" "$IMAGE_PATH"
      echo "Wallpaper updated successfully: $TITLE"

      # Set wallpaper using swww
      if [ -n "''${XDG_RUNTIME_DIR:-}" ]; then
        if [ -z "''${WAYLAND_DISPLAY:-}" ]; then
          if [ -S "$XDG_RUNTIME_DIR/wayland-1" ]; then
            export WAYLAND_DISPLAY="wayland-1"
          elif [ -S "$XDG_RUNTIME_DIR/wayland-0" ]; then
            export WAYLAND_DISPLAY="wayland-0"
          fi
        fi

        if [ -n "''${WAYLAND_DISPLAY:-}" ]; then
          echo "Setting wallpaper via swww..."
          if ! ${swww} img "$IMAGE_PATH" --transition-type fade --transition-duration 2; then
            echo "swww wallpaper command failed."
          fi
        else
          echo "Skipping swww; WAYLAND_DISPLAY unavailable."
        fi
      fi
    '';
    serviceConfig = {
      Type = "oneshot";
      User = config.users.users.potb.name;
      Environment = [
        "XDG_RUNTIME_DIR=/run/user/%U"
      ];
    };
    wantedBy = ["graphical.target"];
    wants = ["network-online.target"];
    after = ["network-online.target"];
  };

  systemd.timers.${service-name} = {
    wantedBy = ["timers.target"];
    timerConfig = {
      # Run every hour
      OnCalendar = "hourly";
      # Also run shortly after boot
      OnBootSec = "2min";
      Persistent = true;
      Unit = "${service-name}.service";
    };
  };
}
