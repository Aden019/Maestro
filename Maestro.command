#!/bin/zsh
# Double-click to start Maestro. It opens in Terminal, which holds the camera permission.
cd "${0:A:h}" && exec .venv/bin/python run.py
