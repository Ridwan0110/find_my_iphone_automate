#!/bin/bash

# Move into the directory where this script is located
cd "$(dirname "$0")" || exit

source .venv/bin/activate
python find_my_iphone_automate.py
