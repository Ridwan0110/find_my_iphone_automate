#!/bin/bash

# Define the tmux session name
SESSION_NAME="find-my-iphone-automate"

# Check if running inside a tmux session
if [ -z "$TMUX" ]; then
  # If not in tmux, create a new detached session and execute this script inside it
  echo "Starting tmux session '$SESSION_NAME' and running script..."
  tmux new-session -d -s "$SESSION_NAME" "bash $(basename "$0")"
  echo "Script started in tmux session '$SESSION_NAME'."
  echo "To attach: tmux attach -t $SESSION_NAME"
  exit 0
fi

# If we are inside a tmux session (either newly created or existing)
echo "Activating virtual environment..."
source .venv/bin/activate

echo "Running main.py..."
python main.py
