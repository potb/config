{
  config,
  pkgs,
  ...
}:
let
  service-name = "update-hubble-potw-wallpaper";
in
{
  systemd.services.${service-name} = {
    description = "Update ESA Hubble Picture of the Week Wallpaper";
    enableStrictShellChecks = true;
    script =
      let
        curl = "${pkgs.curl}/bin/curl";
        feh = "${pkgs.feh}/bin/feh";
        grep = "${pkgs.gnugrep}/bin/grep";
        sort = "${pkgs.coreutils}/bin/sort";
        tail = "${pkgs.coreutils}/bin/tail";
        head = "${pkgs.coreutils}/bin/head";
      in
      ''
        set -eu

        IMAGE_DIR="$HOME/Pictures/hubble-potw"
        IMAGE_PATH="$IMAGE_DIR/hubble-potw.jpg"
        TEMP_IMAGE_PATH="$IMAGE_DIR/hubble-potw_temp.jpg"
        LISTING_URL="https://esahubble.org/images/potw/"

        mkdir -p "$IMAGE_DIR"

        echo "Fetching ESA Hubble Picture of the Week..."

        RETRY_COUNT=0
        MAX_RETRIES=3
        SUCCESS=false

        while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
          if LISTING_PAGE=$(${curl} -sL --max-time 10 "$LISTING_URL"); then
            SUCCESS=true
          else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
              echo "Listing page fetch failed, retrying in 5 seconds... ($RETRY_COUNT/$MAX_RETRIES)"
              sleep 5
            fi
          fi
        done

        if [ "$SUCCESS" = "false" ]; then
          echo "Failed to fetch listing page after $MAX_RETRIES attempts. Keeping existing wallpaper."
          exit 0
        fi

        POTW_PATH=$(echo "$LISTING_PAGE" | ${grep} -oE '/images/potw[0-9]+a/' | ${head} -n1)
        if [ -z "$POTW_PATH" ]; then
          echo "No POTW link found on listing page. Keeping existing wallpaper."
          exit 0
        fi

        LATEST_URL="https://esahubble.org$POTW_PATH"
        echo "Latest POTW page: $LATEST_URL"

        RETRY_COUNT=0
        SUCCESS=false

        while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
          if POTW_PAGE=$(${curl} -sL --max-time 10 "$LATEST_URL"); then
            SUCCESS=true
          else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
              echo "POTW page fetch failed, retrying in 5 seconds... ($RETRY_COUNT/$MAX_RETRIES)"
              sleep 5
            fi
          fi
        done

        if [ "$SUCCESS" = "false" ]; then
          echo "Failed to fetch POTW page after $MAX_RETRIES attempts. Keeping existing wallpaper."
          exit 0
        fi

        IMAGE_URL=$(echo "$POTW_PAGE" | ${grep} -oE 'https://cdn\.esahubble\.org/[^"]+\.jpg' | ${sort} -V | ${tail} -n1)
        if [ -z "$IMAGE_URL" ]; then
          echo "No image URL found on POTW page. Keeping existing wallpaper."
          exit 0
        fi

        echo "Downloading image from: $IMAGE_URL"

        RETRY_COUNT=0
        SUCCESS=false

        while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
          if ${curl} -sL --max-time 30 "$IMAGE_URL" -o "$TEMP_IMAGE_PATH"; then
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

        # Verify file exists and has content
        if [ ! -s "$TEMP_IMAGE_PATH" ]; then
          echo "Downloaded file is empty. Keeping existing wallpaper."
          rm -f "$TEMP_IMAGE_PATH"
          exit 0
        fi

        # Update wallpaper
        mv "$TEMP_IMAGE_PATH" "$IMAGE_PATH"
        echo "Wallpaper updated successfully!"

        # Set wallpaper using feh
        ${feh} --bg-max "$IMAGE_PATH"
      '';
    serviceConfig = {
      Type = "oneshot";
      User = config.users.users.potb.name;
      Environment = [
        "DISPLAY=:0"
        "XAUTHORITY=/home/${config.users.users.potb.name}/.Xauthority"
      ];
    };
    wantedBy = [ "graphical.target" ];
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ];
  };

  systemd.timers.${service-name} = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "hourly"; # Run every hour
      Persistent = true;
      Unit = "${service-name}.service";
    };
  };
}
