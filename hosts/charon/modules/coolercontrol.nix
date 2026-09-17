{
  lib,
  pkgs,
  ...
}: let
  inherit (builtins) listToAttrs map toString;
  toml = pkgs.formats.toml {};

  caseFanCurve = [
    {
      temp = 30.0;
      speed = 25;
    }
    {
      temp = 31.0;
      speed = 30;
    }
    {
      temp = 35.0;
      speed = 40;
    }
    {
      temp = 40.0;
      speed = 50;
    }
    {
      temp = 45.0;
      speed = 70;
    }
    {
      temp = 50.0;
      speed = 100;
    }
  ];

  aioPumpCurve = [
    {
      temp = 34.0;
      speed = 40;
    }
    {
      temp = 35.0;
      speed = 50;
    }
    {
      temp = 40.0;
      speed = 60;
    }
    {
      temp = 45.0;
      speed = 75;
    }
    {
      temp = 50.0;
      speed = 100;
    }
    {
      temp = 55.0;
      speed = 100;
    }
  ];

  hysteresis = {
    threshold = 3.0;
    downwardOnly = true;
    rampDown = {
      stepMin = 2;
      stepMax = 5;
    };
    responseDelay = 1;
    dutyRange = {
      min = 5;
      max = 100;
    };
  };

  krakenLcd = {
    mode = "liquid";
    brightness = 50;
    orientation = 0;
  };

  curveToProfile = map (p: [
    p.temp
    p.speed
  ]);

  mkGraphProfile = {
    id,
    name,
    curve,
  }: {
    uid = id;
    inherit name;
    p_type = "Graph";
    speed_profile = curveToProfile curve;
    temp_source = {
      temp_name = "liquid";
      device_uid = hw.kraken;
    };
    temp_min = (lib.head curve).temp;
    temp_max = (lib.last curve).temp;
    function_uid = profileIds.silentHysteresis;
    offset_profile = [];
  };

  mkHysteresisFunction = {
    uid = profileIds.silentHysteresis;
    name = "Silent Hysteresis";
    f_type = "Standard";
    duty_minimum = hysteresis.dutyRange.min;
    duty_maximum = hysteresis.dutyRange.max;
    step_size_min_decreasing = hysteresis.rampDown.stepMin;
    step_size_max_decreasing = hysteresis.rampDown.stepMax;
    response_delay = hysteresis.responseDelay;
    deviance = hysteresis.threshold;
    only_downward = hysteresis.downwardOnly;
    threshold_hopping = true;
  };

  assignToFans = profileId: count:
    listToAttrs (
      map (n: {
        name = "fan${toString n}";
        value.profile_uid = profileId;
      }) (lib.range 1 count)
    );

  hw = {
    acpitz = "f42333b13a2853dfb8e516c576470622e74a4659bfffe7ca229f68733beae979";
    intel = "0280f15bb4062803de46685e1d7a231b3a1a5e74b1fbb2b639623ab469a075f6";
    aura = "f226946857a3141b80fefa0bae8de91cdba1c6eedf91d96ea7bef76ce88b4e90";
    amdgpu = "7442ece48a26c31e110bbb1d21577e4a7b4613be5cce8adee1fe2d0832d11696";
    custom = "19e098e312e1b1b39163a343ea22b6ea17f18ec1a803ffe0ce44f5bacd6076ee";
    kraken = "f4f3f53c719f493d54b54402bcb5ca2f3f2d992edf39c4530ff586786b794da4";
    nvme = "da3ff8eb14e32f9990cace5875430447b86c8a25d4b6d91a795febb4173cef4a";
    iwlwifi = "33f022b13ddcf5eef2951eec6ee8e408eabdf92b3ae22bbc7d2c06decea183cb";
    kraken-hwmon = "eeeeb43075dec99410f7298266b3dfb51bf783cc9355ebb2191f2e93e6b375c4";
    nct6798 = "00a4da18625f56275c89e2fcd25a83c08c5ad3326452fa7e252fcc8a89c92493";
    spd5118 = [
      "b5532289feaa0fa841026f9a990d69d5a1cf1dc94f3bf59db358bf0db785e0c2"
      "0b17d9ebe9dc780d1b76af7cddc68a0a09e8e7f3f829dbe826a8b9f3c2ae6aea"
      "fda8de9a9f0a32024288a081f4a31e58996e38e36130ace16d092524fe0e84cb"
      "ee0068a5c1b0c8a64c78a15e8a797e6e52c8a062161e65fe96b61539d9d1dbc0"
      "ef2abfccc2d6be1357ae7dca5d4a378b639af814afe7570e1fcc9bb7216ee44f"
      "be4cd1134c4c07a8ece957f3fdb5a7529a0cfcbc87508140b3ebdc274a07ce2d"
    ];
  };

  profileIds = {
    caseFans = "8b2c6b38-a189-4a26-8b42-7ff73a739e55";
    aioPump = "92f094b5-2f4d-4fa3-b951-3d9f292b3414";
    silentHysteresis = "e6f8d67e-ab79-4456-8323-a9deff4235fa";
  };

  deviceRegistry =
    {
      ${hw.acpitz} = "acpitz";
      ${hw.intel} = "Intel(R) Core(TM) i9-14900K";
      ${hw.aura} = "ASUS Aura LED Controller";
      ${hw.amdgpu} = "amdgpu";
      ${hw.custom} = "Custom Sensors";
      ${hw.kraken} = "NZXT Kraken 2023";
      ${hw.nvme} = "nvme";
      ${hw.iwlwifi} = "iwlwifi_1";
      ${hw.kraken-hwmon} = "kraken2023";
      ${hw.nct6798} = "nct6798";
    }
    // listToAttrs (
      map (id: {
        name = id;
        value = "spd5118";
      })
      hw.spd5118
    );

  configFile = toml.generate "coolercontrol-config.toml" {
    devices = deviceRegistry;
    legacy690 = {};

    device-settings = {
      ${hw.amdgpu}.fan1.profile_uid = "0";

      ${hw.kraken} = {
        fan.profile_uid = profileIds.aioPump;
        pump.profile_uid = profileIds.aioPump;
        lcd.lcd =
          krakenLcd
          // {
            colors = [];
          };
      };

      ${hw.nct6798} = assignToFans profileIds.caseFans 7;
    };

    profiles = [
      {
        uid = "0";
        name = "Default Profile";
        p_type = "Default";
        function = "0";
      }
      (mkGraphProfile {
        id = profileIds.caseFans;
        name = "Case fans";
        curve = caseFanCurve;
      })
      (mkGraphProfile {
        id = profileIds.aioPump;
        name = "AIO pump";
        curve = aioPumpCurve;
      })
    ];

    functions = [
      {
        uid = "0";
        name = "Default Function";
        f_type = "Identity";
      }
      mkHysteresisFunction
    ];

    settings = {
      apply_on_boot = true;
      liquidctl_integration = true;
      hide_duplicate_devices = true;
      no_init = false;
      startup_delay = 2;
      thinkpad_full_speed = false;
      compress = false;
      drivetemp_suspend = false;
    };
  };
in {
  programs.coolercontrol.enable = true;

  systemd.tmpfiles.rules = [
    "d /etc/coolercontrol 0755 root root -"
    "C /etc/coolercontrol/config.toml 0644 root root - ${configFile}"
  ];
}
