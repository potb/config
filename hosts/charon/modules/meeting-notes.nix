{
  services.meeting-notes = {
    backend = "native";
    model = "large-v3";
    live = true;
    retentionDays = null;
    privateData = true;
    slack = {
      enable = true;
      postTo = "dm";
      userId = "U0C228DMEV9";
      channelId = "C0C23NA7EKX";
    };
  };
}
