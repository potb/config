{
  services.pulseaudio.enable = false;

  security.rtkit.enable = true;

  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    wireplumber.enable = true;

    extraConfig.pipewire = {
      "01-buffer-underrun" = {
        link.max-buffers = 64;
      };

      "02-low-latency" = {
        "context.properties" = {
          "default.clock.rate" = 48000;
          "default.clock.quantum" = 64;
          "default.clock.min-quantum" = 64;
          "default.clock.max-quantum" = 128;
        };
      };

      "03-mono-upmix" = {
        "context.properties" = {
          "channelmix.upmix" = true;
        };
      };
    };
  };
}
