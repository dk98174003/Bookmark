#!/usr/bin/env bash
set -euo pipefail

# Install fpm (Effing Package Management) on Linux Mint / Ubuntu.
# Source: fpm docs + common Ubuntu/Mint install method.
#
# Run:
#   chmod +x install_fpm.sh
#   ./install_fpm.sh
#
# Verify:
#   fpm --version

echo "[1/3] Updating apt index..."
sudo apt update

echo "[2/3] Installing prerequisites (ruby + build tools)..."
sudo apt install -y ruby ruby-dev build-essential rubygems

echo "[3/3] Installing fpm via RubyGems..."
sudo gem install --no-document fpm

echo
echo "Done. Version:"
fpm --version
