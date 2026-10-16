# Diagnosing a Steam game on charon

The tools live in `hosts/charon/modules/gaming.nix`. This page is the order in
which to use them when a game will not start or runs badly.

## Tools

| Tool | Use |
|------|-----|
| `mangohud` | FPS and frame time overlay. Launch option `mangohud %command%`, Vulkan and OpenGL games only |
| `amdgpu_top` | Live GPU load, clocks and VRAM per process, `amdgpu_top --smi` for a one-screen summary |
| `nvtop` | GPU load history next to CPU |
| `pidstat` | Per-process and per-thread CPU over time, `pidstat -t -p <pid> 5` |
| `file` | Tells a Linux ELF from a Windows PE, which answers "native or Proton" |
| `protontricks` | Installs Windows runtimes such as `webview2` into a Proton prefix |
| `steam-run` | FHS environment. `SteamLinuxRuntime_*/run` fails outside it with `bwrap: execvp true` |
| `grim` | Screenshot of the desktop to check what the window actually shows |

## Where the logs are

- `~/.local/share/Steam/logs/console-linux.txt`: stdout and stderr of every game, plus Proton and pressure-vessel output
- `~/.local/share/Steam/logs/gameprocess_log.txt`: the exact launch command, so whether it went through Proton or the Linux runtime
- `~/.local/share/Steam/logs/compat_log.txt`: which compatibility tool Steam mapped to the app
- `~/.local/share/Steam/steamapps/appmanifest_<appid>.acf`: install dir and build

## Won't start

1. Read the launch command in `gameprocess_log.txt`. A `proton waitforexitandrun ... game.exe` line for a game that ships a Linux build means a forced compatibility tool. Untick it under Properties, Compatibility.
2. `file` on the binary in `steamapps/common/<game>` confirms which build is installed.
3. Run the game by hand to see the real error: `steam-run ~/.local/share/Steam/steamapps/common/SteamLinuxRuntime_4/run -- ./<binary>` from the game directory, with `SteamAppId=<appid>` set. Running the binary bare fails on NixOS with missing `libX11.so.6` and is not a real signal.

## Runs slowly

1. Measure before changing anything: `pidstat -p <pid> 5` for CPU, `amdgpu_top` for GPU. High CPU with an idle GPU means rendering fell back to software.
2. For Vulkan and OpenGL games, add `mangohud %command%` to see FPS directly.
3. Change one launch option at a time and measure again on the same scene.

## Tauri and WebKitGTK games

Some games, such as Birb, are web apps in a Tauri shell. They render through
WebKitGTK, `mangohud` cannot see them, and the default is often CPU canvas
rendering. Signs: a `WebKitWebProcess` child holding several cores.

- Search the binary for its own switches: `grep -a -o -E '[A-Z]+_[A-Z0-9_]{4,}' <binary> | sort -u`
- Useful WebKitGTK variables: `WEBKIT_DISABLE_DMABUF_RENDERER`, `WEBKIT_DISABLE_COMPOSITING_MODE`, `WEBKIT_DMABUF_RENDERER_FORCE_SHM`, `WEBKIT_SHOW_FPS=1`

### Birb (4364930)

Launch options, measured at roughly 250% CPU before and 35% after with the GPU
around 12%:

```
BIRB_LINUX_CANVAS_ACCELERATION=1 WEBKIT_DMABUF_RENDERER_FORCE_SHM=0 %command%
```

The game writes its own log to `~/.local/state/birb/console-linux.txt`. The
`canvas_graphics ... accelerated_2d=` line there confirms whether the switch took.
