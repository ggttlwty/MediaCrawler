#!/bin/bash

# This script automates the setup process for MediaCrawler on a Debian-based Linux system.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- 1. Updating package lists ---"
sudo apt-get update

echo "--- 2. Installing system dependencies (Python, Node.js, pip) ---"
sudo apt-get install -y python3 python3-pip nodejs npm curl

echo "--- 3. Installing uv (Python package manager) ---"
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
echo "uv installed. Please run 'source ~/.bashrc' or restart your terminal to update PATH if uv command is not found."

echo "--- 4. Installing Python dependencies using uv ---"
uv sync

echo "--- 5. Installing Playwright browser system dependencies ---"
uv run playwright install-deps

echo "--- 6. Downloading Playwright browsers ---"
uv run playwright install

echo "--- Setup complete! ---"
echo "You can now run the crawler. Recommended command for headless servers:"
echo "uv run main.py --platform xhs --lt cookie --type search"
echo "Remember to set HEADLESS = True in config/base_config.py and provide your COOKIES."
