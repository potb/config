{fetchurl}: {
  large-v3 = fetchurl {
    url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin";
    sha256 = "1qnijhsv47x1vx2vixy4jr8n0k6q8ham9ggrqh1m53dr82s85lb4";
  };
  large-v3-turbo = fetchurl {
    url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin";
    sha256 = "0sdwwblbfy9qjkjjxxvyfn47rx3y6pm1wfdcjfcidsrq9mvhziqz";
  };
  silero-vad = fetchurl {
    url = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin";
    sha256 = "1kx29v0b93x235cqgr17y110lby7yzng72g4bk8gp49bsjc0v519";
  };
}
