# Echolocation

Concept demo — you navigate a dark map blind. Click to ping, and sound waves travel out, bounce off walls, and reveal them as they return. Closer walls light up first.

No enemies, no goal. Just the mechanic.

---

## How it works

**Ping** — casts 240 rays (every 1.5°) from the player. Each ray finds the closest wall using parametric line-segment intersection math. Every hit schedules a reveal after `distance / SOUND_SPEED` seconds — so the reveal ripples outward in time, not just space.

**Revelation** — when a return wave arrives, it creates a 20px wall segment centered on the hit point. Brightness scales with distance: closer hits are brighter. Each segment fades over 2 seconds.

**Sonar lines** — thin lines are drawn from your current position to each revealed hit point. If you move behind a wall, the lines to the other side are clipped and disappear — handled by running a secondary ray-cast from the player to each hit point every frame.

**Auto-ping** — press `T` to toggle continuous pinging at 20 pings/second.

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
