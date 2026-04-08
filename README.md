# Echolocation

Concept demo. The screen is black. Click to ping — after a short delay, dots appear on nearby walls, then further ones, timed by distance. They fade after 2 seconds.

No enemies, no goal. Just the mechanic.

---

## How it works

**Ping** — casts 240 rays from the player (every 1.5°). Each ray finds the nearest wall using parametric line-segment intersection. Each hit is scheduled to reveal after `distance / SOUND_SPEED` seconds — so closer walls show up first.

**What you see** — small dots on the wall at each hit point. Brightness depends on distance (closer = brighter). Faint lines connect the player to each dot. If you move behind a wall, the lines to dots on the other side disappear — a second ray-cast per dot checks line of sight every frame.

**Fading** — dots fade over 2 seconds. Ping again to refresh them.

**Auto-ping** — press `T` to ping 20 times per second continuously.

---

## Controls

| Input | Action |
|---|---|
| Left click | Ping |
| WASD / Arrows | Move |
| `T` | Toggle auto-ping |
| `Esc` | Quit |

---

## Running it

```bash
pip install pygame numpy
python echolocation_game.py
```

**605 lines**, single file.
