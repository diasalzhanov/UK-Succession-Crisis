#!/bin/bash
# Double-click to run your own analysis (settings are at the top of explore.py).
cd "$(dirname "$0")"
python3 explore.py
read -n 1 -s -r -p "Press any key to close"
