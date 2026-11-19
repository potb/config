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
  silero-vad-onnx = fetchurl {
    url = "https://huggingface.co/istupakov/silero-vad-onnx/resolve/b3e3ee3cce4c11ceb63b1a0b229d916069c1ddf6/silero_vad.onnx";
    sha256 = "1qw8hyfjfrac2xz2ns4895dv5pp8hndnyzg6jhm2k7jhyhi3l58s";
  };
  wespeaker-resnet34 = fetchurl {
    url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx";
    sha256 = "157yaz94akv6aw5dw15n70x1hzmxvzkg9dm6119k6lqlvalhiwjy";
  };
}
