# Maestro

Conduct your Mac: hold a hand gesture in front of the camera to open an app. Everything runs on this Mac.

## Run it

Double-click `Maestro.command`, or start it from the Terminal app so macOS can ask for camera permission:

```bash
cd ~/Desktop/websites/Maestro && .venv/bin/python run.py
```

To preview the interface with a pretend hand, no camera, and no apps opening, add `--demo`.

## Gestures

Maestro starts asleep, so apps can't open until you wake it.

| Gesture | Action |
|---|---|
| Closed fist, held for 1 second | Wake |
| Thumbs up or rock sign (your choice), held for 1 second | Sleep |
| Two fingers, held briefly | Safari |
| Three fingers, held briefly | Notes |
| Thumb and little finger, held briefly | Music |
| Point | Move the cursor |
| Pinch thumb and index while pointing | Click, or hold to drag |
| Open hand, moved up or down | Scroll |

Click an app's name in the interface to change it. Your choices are saved in `config.json`.

The air cursor also needs Accessibility permission for Terminal, which Maestro asks for in its window.

## Status

- Working: the interface, demo mode, gesture logic (`.venv/bin/python -m pytest`), and opening apps.
- Being tuned on a real hand: the finger thresholds in `maestro/gestures.py`, and the pinch and scroll settings in `maestro/pointer.py`.
