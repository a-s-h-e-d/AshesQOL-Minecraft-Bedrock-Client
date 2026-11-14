# AshesQOL

A quality-of-life overlay for **Minecraft: Bedrock Edition (Windows)**, written in Python.

AshesQOL runs as a separate program next to the game. It reads the game's memory and draws its modules in a
transparent, click-through window on top of Minecraft. You control everything from a Future/Meteor-style click GUI
or a classic settings window.

> **Disclaimer.** This is an independent project, not affiliated with or endorsed by Mojang or Microsoft.
> Showing information the game normally hides (for example through walls) counts as cheating on most servers and
> Realms, and may break server rules or Minecraft's terms of use. Use AshesQOL in single-player or in worlds where
> everyone agrees to it. Modules that write to the game's memory say so in their description: keep those to
> single-player. You use this software at your own risk.

---

## Features

### Modules

| Module | What it does |
|---|---|
| **HUD** | Watermark, coordinates, Nether/Overworld coordinates for your current dimension, facing direction, FPS, list of enabled modules. Custom or RGB accent color. |
| **ESP** | 2D or 3D boxes around players, hostile mobs, passive mobs and items, with health bars. |
| **Tracers** | Lines to entities, including arrows toward entities that are off-screen. |
| **Nametags** | Name, health and distance above entities. |
| **BlockESP** | Highlights chosen blocks (chests, spawners, ores, …) through walls. Includes a searchable block picker with per-block colors. Only shows blocks from your current dimension. |
| **Freecam** | Detach the camera and fly it around with WASD; you snap back when you turn it off. Single-player only. |
| **ClickGUI** | Colors, RGB mode, background dimming and font of the click GUI. |

### Everything else

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

Dependencies: [PyQt6](https://pypi.org/project/PyQt6/) for the windows and overlay,
[pymem](https://pypi.org/project/Pymem/) for reading the game's memory, and [numpy](https://numpy.org/) for the
automatic offset update.

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
| Block data, for modules that show blocks (first time) | ~35 s | ~40 s |

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
- In settings, sliders can be dragged, options cycle with left- and right-click, and colors and lists open a picker.
- **Drag** a panel by its header. **Right-click** a header to collapse it. **Scroll** over a long panel to move it.
- **Esc** or **Right Shift** closes the GUI and gives focus back to Minecraft. In single-player, Bedrock may show its
  pause menu when the GUI opens; press Esc in-game after closing.

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
| Status says **UNSUPPORTED VERSION** | Minecraft updated and the offsets haven't been updated yet. See [Game updates](#game-updates). |
| Status says **Not in a world** for a long time | Check your game version. The offsets only match 1.26.63. On Realms, wait up to ~40 s. |
| Overlay doesn't appear over the game | Use windowed or borderless mode, and check that **Data source** is **Memory**. |
| Boxes are offset from mobs | Match **Game FOV** to the game. Sprinting, flying and view bobbing change the in-game FOV. |
| Boxes trail when turning, right after joining | Normal for the first ~30 s, until the camera is found (see the on-screen notice). |
| Antivirus warning | Reading another process's memory is what AshesQOL does. Some antivirus tools flag that behaviour. |

## Game updates

Minecraft updates usually move things around in memory. AshesQOL checks the game's exact build (for example
`1.26.63.1`) against the build its offsets were made for.

When they differ, AshesQOL asks what to do:

- **Update automatically**: join a world (single-player or a Realm) first. AshesQOL then searches the game's memory
  and re-finds every value, which takes about 2–3 minutes in the background with progress shown on screen. It only
  saves the new values if they all check out, and keeps the old ones as a backup (`offsets.<old version>.json`).
  You can also start this any time with **Update offsets…** in the settings window.
- **Try anyway**: keep the current offsets. Sometimes a small hotfix doesn't move anything.
- **Not now**: the status shows **UNSUPPORTED VERSION**, and AshesQOL doesn't search memory, because that couldn't
  succeed.

The automatic update re-finds the *identifiers* that move with every build. If an update also changes how data is
laid out inside the game's objects, it stops and says so, and the offsets need a manual update.

Everything version-specific is in one file,
[`ashesqol/data/offsets.json`](ashesqol/data/offsets.json): class identifiers (vtables), field offsets and data
layouts. [`docs/recon-1.26.63.md`](docs/recon-1.26.63.md) documents what each value is and how it was found.

## How it works

- **Overlay**: a transparent, click-through, always-on-top Qt window placed exactly over Minecraft's client area.
- **Memory reading**: pymem with `ReadProcessMemory`. Read-only, except for modules that say they write.
- **Finding the player**:
  - single-player: by its object signature at a fixed spot in a heap segment
  - Realms: through the game's entity list (an EnTT component storage)
- **Entities**: read from that list. Positions are blended between ticks the way the game does it.
- **Camera**: a separate per-frame rotation component is read, so the overlay turns with your view rather than with
  the 20-per-second game tick.
- **Blocks**: a background thread walks the loaded chunks:
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
  game/                    data providers, memory reader, block scanner, camera, offset update, 3D math
  modules/                 one file per module (see the table above)
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

[MIT](LICENSE) © 2026 a-s-h-e-d

The Minecraft font option uses `Mojangles.ttf` from your own Minecraft installation. The font belongs to
Mojang and isn't part of this project or its license.
