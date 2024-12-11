let
  port = 11434;
in {
  services.ollama = {
    enable = true;
    port = port;
    acceleration = "rocm";
    rocmOverrideGfx = "11.0.0";
  };

  services.open-webui = {
    enable = true;
    environment.OLLAMA_API_BASE_URL = "http://localhost:${toString port}";
    environment.WEBUI_AUTH = "False";
  };
}
