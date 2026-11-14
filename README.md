# AshesQOL

A quality-of-life overlay for **Minecraft: Bedrock Edition (Windows)**, written in Python.

AshesQOL runs as a separate program next to the game. It reads the game's memory (read-only) and draws ESP boxes,
tracers, nametags, a HUD and highlighted blocks in a transparent, click-through window on top of Minecraft. It comes
with a Future/Meteor-style click GUI and a classic settings window.

> **Disclaimer.** This is an independent project, not affiliated with or endorsed by Mojang or Microsoft.
> Features like ESP and BlockESP count as cheats on most servers and Realms, and using them there may break server
> rules or Minecraft's terms of use. Use AshesQOL in single-player or in worlds where everyone agrees to it.
> Freecam writes to the game's memory: keep it to single-player. You use this software at your own risk.

---

## Features

| Module | What it does |
|---|---|
| **HUD** | Watermark, coordinates, Nether/Overworld coordinates for your current dimension, facing direction, FPS, list of enabled modules. Custom or RGB accent color. |
| **ESP** | 2D or 3D boxes around players, hostile mobs, passive mobs and items, with health bars. |
| **Tracers** | Lines to entities, including arrows toward entities that are off-screen. |
| **Nametags** | Name, health and distance above entities. |
| **BlockESP** | Highlights chosen blocks (chests, spawners, ores, …) through walls. Includes a searchable block picker with per-block colors. Only shows blocks from your current dimension. |
| **Freecam** | Detach the camera and fly it around with WASD; you snap back when you turn it off. Single-player only. |
| **ClickGUI** | Colors, RGB mode, background dimming and font of the click GUI. |

The rest of the app:

- **Click GUI** (Right Shift) with draggable category panels and inline settings. There's also a full **settings
  window** (Insert).
- **Smooth rendering**:
  - Positions are interpolated between game ticks.
  - The game's per-frame camera rotation is read, so boxes stick to targets while you turn.
  - Memory reading happens on its own thread, so slow reads never stall a frame.
- **Customizable look**: accent colors, an RGB mode that rolls down the screen, and the **Minecraft font**. The font
  is loaded from your own game installation at runtime and is never bundled with AshesQOL.
- Works in **single-player and on Realms**.
- A **master on/off switch** (End) that stops everything at once.

## Requirements

- Windows 10 or 11
- Minecraft: Bedrock Edition for Windows, **version 1.26.63**. The memory offsets are version-specific, see
  [Game updates](#game-updates).
- Python **3.11 or newer** (developed on 3.13)

## Installation

```powershell
git clone https://github.com/a-s-h-e-d/AshesQOL-Minecraft-Bedrock-Client.git
cd AshesQOL-Minecraft-Bedrock-Client
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Dependencies: [PyQt6](https://pypi.org/project/PyQt6/) for the windows and overlay, and
[pymem](https://pypi.org/project/Pymem/) for reading the game's memory.

## Usage

```powershell
.venv\Scripts\activate
python main.py
```

1. Start Minecraft and join a world. Use **windowed or borderless fullscreen**: an exclusive-fullscreen game can draw
   over the overlay.
2. In the AshesQOL window, set **Data source** to **Memory (Minecraft)**.
   **Mock (demo data)** shows a preview with fake entities, which is handy for trying settings without the game.
3. Set **Game FOV** to the FOV in Minecraft's video settings so boxes line up.
4. Turn modules on in the settings window, or press **Right Shift** in-game to open the click GUI.

### First-time waits

AshesQOL finds the game's data by searching memory, which takes a moment after joining a world. A notice at the top of
the screen shows what it's still looking for:

| What | Single-player | Realms |
|---|---|---|
| Your player and nearby entities | under a second | up to ~40 s |
| Per-frame camera (smooth turning) | ~30 s | ~30 s |
| BlockESP chunk data (first time) | ~35 s | ~40 s |

### Hotkeys

| Key | Action |
|---|---|
| **Right Shift** | Open or close the click GUI (while Minecraft is focused) |
| **Insert** | Show or hide the settings window |
| **End** | Turn all of AshesQOL on or off |
| *your choice* | Toggle a module: set a keybind per module in either GUI |

All three keys can be changed in the settings window under **Hotkeys**. Left Shift isn't the default for the click GUI
because it's the sneak key.

### Click GUI

- **Left-click** a module to turn it on or off. **Right-click** it to show its settings.
- In settings, sliders can be dragged, options cycle with left- and right-click, and colors and the block list open a
  picker.
- **Drag** a panel by its header. **Right-click** a header to collapse it. **Scroll** over a long panel to move it.
- **Esc** or **Right Shift** closes the GUI and gives focus back to Minecraft. In single-player, Bedrock may show its
  pause menu when the GUI opens; press Esc in-game after closing.

### Freecam

1. Turn Freecam on. In single-player, its WASD mode takes **W/A/S/D, Space, Shift and Ctrl** away from Minecraft while
   it's on, so your real player stays put.
2. Fly with **W/A/S/D**, go up and down with **Space/Shift**, and hold **Ctrl** for 4× speed. The mouse looks around
   as usual.
3. Turn Freecam off to snap back to where you started.

## Configuration

Settings are saved to `config/settings.json` when you click **Save** or close AshesQOL. This includes module settings,
keybinds, hotkeys and click GUI panel positions. Delete the file to reset everything.

Useful options in the settings window:

- **Show this window when AshesQOL starts**: turn it off to start with only the overlay and click GUI.
- **Only show overlay while Minecraft is focused**
- **Smooth movement between game ticks**

`max_fps` in `config/settings.json` caps the overlay's redraw rate. The default `0` matches your monitor.

## Troubleshooting

| Problem | Try |
|---|---|
| Status says **attach failed** | Run the terminal or IDE **as administrator**. |
| HUD says **Not in a world** for a long time | Check your game version. The offsets only match 1.26.63. On Realms, wait up to ~40 s. |
| Overlay doesn't appear over the game | Use windowed or borderless mode, and check that **Data source** is **Memory**. |
| Boxes are offset from mobs | Match **Game FOV** to the game. Sprinting, flying and view bobbing change the in-game FOV. |
| Boxes trail when turning, right after joining | Normal for the first ~30 s, until the camera is found (see the on-screen notice). |
| Antivirus warning | Reading another process's memory is what AshesQOL does. Some antivirus tools flag that behaviour. |

## Game updates

Minecraft updates usually move things around in memory. Everything version-specific is in one file,
[`ashesqol/data/offsets.json`](ashesqol/data/offsets.json): class identifiers (vtables), field offsets and data
layouts. [`docs/recon-1.26.63.md`](docs/recon-1.26.63.md) documents what each value is and how it was found.

AshesQOL also tries to adapt by itself where it can. For example, it works out new block-storage layouts at runtime.

## How it works

- **Overlay**: a transparent, click-through, always-on-top Qt window placed exactly over Minecraft's client area.
- **Memory reading**: pymem with `ReadProcessMemory`, read-only. The only exception is Freecam, which writes the
  client-side player position.
- **Finding the player**:
  - single-player: by its object signature at a fixed spot in a heap segment
  - Realms: through the game's entity list (an EnTT component storage)
- **Entities**: read from that list. Positions are blended between ticks the way the game does it.
- **Camera**: a separate per-frame rotation component is read, so the overlay turns with your view rather than with
  the 20-per-second game tick.
- **BlockESP**: a background thread walks the loaded chunks:
  1. read each 16×16×16 section's palette
  2. skip sections without a wanted block
  3. decode only the ones that have one
- **Threads**: a reader thread polls the game about 250 times a second. The UI thread only draws, so a slow memory read
  never causes a stutter.

## Project layout

```
main.py                    entry point
ashesqol/
  app.py                   wires everything together, per-frame loop, hotkeys
  config.py                settings file
  core/                    process attach, memory search helpers, Win32 bits, keyboard hook
  game/                    data providers, memory reader, block scanner, camera, 3D math
  modules/                 HUD, ESP, Tracers, Nametags, BlockESP, Freecam, ClickGUI theme
  ui/                      overlay, click GUI, settings window, block picker, fonts, theme
  data/offsets.json        version-specific memory layout
docs/                      notes on the game's memory layout
```

## Adding a module

1. Subclass `ashesqol.modules.base.Module`.
2. Declare settings in `setup()` with `self.add(...)`.
3. Draw in `on_render(ctx)`, or act in `on_tick(ctx)`.
4. Add it to `create_modules()` in `ashesqol/modules/__init__.py`.

Both GUIs build their controls from the settings automatically.

## License

No license has been chosen yet, so all rights are reserved for now.
