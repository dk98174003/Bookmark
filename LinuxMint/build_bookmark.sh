#!/usr/bin/env bash
set -euo pipefail

# Build a .deb for Linux Mint / Ubuntu using fpm (dir -> deb).
# Installs into /opt/bookmark-client and provides:
#   - /usr/local/bin/bookmark-client  (launcher)
#   - /usr/share/applications/bookmark-client.desktop
#   - /usr/share/icons/hicolor/.../apps/bookmark-client.(png|svg)
#   - /usr/share/pixmaps/bookmark-client.png (fallback for some desktops)
#
# Dependencies declared:
#   - python3
#   - python3-tk   (tkinter)
#   - xdg-utils    (xdg-open)
#
# Optional env overrides:
#   PKG_NAME=bookmark-client
#   BIN_NAME=bookmark-client
#   ENTRYPOINT=bookmark.py
#   ICON_FILE=/path/to/icon.png   (or relative path)
#   VERSION=2025.12.17.1200

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PKG_NAME="${PKG_NAME:-bookmark-client}"
APP_DIR="/opt/${PKG_NAME}"
BIN_NAME="${BIN_NAME:-bookmark-client}"

ENTRYPOINT="${ENTRYPOINT:-}"
if [[ -z "$ENTRYPOINT" ]]; then
  if [[ -f "bookmark_improved.py" ]]; then
    ENTRYPOINT="bookmark_improved.py"
  elif [[ -f "bookmark.py" ]]; then
    ENTRYPOINT="bookmark.py"
  else
    echo "ERROR: Could not find bookmark_improved.py or bookmark.py in: $PROJECT_DIR"
    echo "Set ENTRYPOINT to your main python file, e.g.:"
    echo "  ENTRYPOINT=main.py ./build_bookmark.sh"
    exit 2
  fi
fi

ARCH="$(dpkg --print-architecture)"
VERSION="${VERSION:-$(date +%Y.%m.%d.%H%M)}"
BUILD_DIR="${BUILD_DIR:-$PROJECT_DIR/build}"
STAGE="${BUILD_DIR}/pkgroot"

DESC="${DESC:-Simple Tkinter bookmark client}"
MAINT="${MAINT:-Knud}"
URL="${URL:-https://it3home.dk}"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: Missing command: $1"; exit 3; }; }

need_cmd fpm
need_cmd python3

echo "Project    : $PROJECT_DIR"
echo "Package    : $PKG_NAME"
echo "Version    : $VERSION"
echo "Arch       : $ARCH"
echo "Entrypoint : $ENTRYPOINT"
echo

echo "[1/7] Cleaning build dir..."
rm -rf "$STAGE"
mkdir -p "$STAGE"

echo "[2/7] Staging application files..."
mkdir -p "$STAGE${APP_DIR}"

# Copy project files while excluding common junk
if command -v rsync >/dev/null 2>&1; then
  rsync -a     --exclude '.venv'     --exclude 'build'     --exclude '__pycache__'     --exclude '*.pyc'     --exclude '.git'     --exclude '.mypy_cache'     --exclude '.pytest_cache'     ./ "$STAGE${APP_DIR}/"
else
  tar --exclude='./.venv'       --exclude='./build'       --exclude='./__pycache__'       --exclude='./.git'       -cf - . | tar -xf - -C "$STAGE${APP_DIR}"
fi

if [[ ! -f "$STAGE${APP_DIR}/${ENTRYPOINT}" ]]; then
  echo "ERROR: Entrypoint not found in staged dir: $STAGE${APP_DIR}/${ENTRYPOINT}"
  exit 5
fi

echo "[3/7] Vendoring Python deps (optional)..."
VENDOR_DIR="$STAGE${APP_DIR}/vendor"
if [[ -f "requirements.txt" ]]; then
  if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "ERROR: requirements.txt exists but pip is not available."
    echo "  sudo apt update && sudo apt install -y python3-pip"
    exit 4
  fi
  mkdir -p "$VENDOR_DIR"
  python3 -m pip install --upgrade pip >/dev/null
  python3 -m pip install --no-compile --no-cache-dir --target "$VENDOR_DIR" -r "requirements.txt"
else
  echo "No requirements.txt found, skipping vendoring."
fi

echo "[4/7] Creating launcher script..."
mkdir -p "$STAGE/usr/local/bin"
cat > "$STAGE/usr/local/bin/${BIN_NAME}" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="__APP_DIR__"
ENTRYPOINT="__ENTRYPOINT__"

# Add vendored deps if present
if [[ -d "${APP_DIR}/vendor" ]]; then
  export PYTHONPATH="${APP_DIR}/vendor:${PYTHONPATH:-}"
fi

exec /usr/bin/python3 "${APP_DIR}/${ENTRYPOINT}" "$@"
SH

sed -i "s#__APP_DIR__#${APP_DIR}#g" "$STAGE/usr/local/bin/${BIN_NAME}"
sed -i "s#__ENTRYPOINT__#${ENTRYPOINT}#g" "$STAGE/usr/local/bin/${BIN_NAME}"
chmod 0755 "$STAGE/usr/local/bin/${BIN_NAME}"

echo "[5/7] Creating desktop entry..."
mkdir -p "$STAGE/usr/share/applications"
cat > "$STAGE/usr/share/applications/${PKG_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bookmark
Comment=${DESC}
Exec=${BIN_NAME}
Terminal=false
Icon=${PKG_NAME}
Categories=Utility;
EOF

echo "[6/7] Installing icon (auto-detect + it4home.png)..."
ICON_FILE="${ICON_FILE:-}"

# Prefer your known icon name if present
if [[ -z "$ICON_FILE" && -f "it4home.png" ]]; then
  ICON_FILE="it4home.png"
fi

# Fallback auto-detect
if [[ -z "$ICON_FILE" ]]; then
  for cand in     "icon.png" "icon.svg"     "it4home.png" "it4home.svg"     "assets/icon.png" "assets/icon.svg"     "resources/icon.png" "resources/icon.svg"     "icons/icon.png" "icons/icon.svg"     "${PKG_NAME}.png" "${PKG_NAME}.svg"
  do
    if [[ -f "$cand" ]]; then
      ICON_FILE="$cand"
      break
    fi
  done
fi

if [[ -n "$ICON_FILE" && ! -f "$ICON_FILE" ]]; then
  echo "WARNING: ICON_FILE was set but not found: $ICON_FILE"
  ICON_FILE=""
fi

install_icon_png() {
  local src_png="$1"
  mkdir -p "$STAGE/usr/share/icons/hicolor/256x256/apps"
  cp -f "$src_png" "$STAGE/usr/share/icons/hicolor/256x256/apps/${PKG_NAME}.png"

  # Fallback location used by some desktop environments/tools
  mkdir -p "$STAGE/usr/share/pixmaps"
  cp -f "$src_png" "$STAGE/usr/share/pixmaps/${PKG_NAME}.png"
}

install_icon_svg() {
  local src_svg="$1"
  mkdir -p "$STAGE/usr/share/icons/hicolor/scalable/apps"
  cp -f "$src_svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/${PKG_NAME}.svg"
}

if [[ -n "$ICON_FILE" ]]; then
  ext="${ICON_FILE##*.}"
  ext="${ext,,}"
  case "$ext" in
    png)
      install_icon_png "$ICON_FILE"
      echo "Installed PNG icon: $ICON_FILE -> ${PKG_NAME}.png (hicolor + pixmaps)"
      ;;
    svg)
      install_icon_svg "$ICON_FILE"
      echo "Installed SVG icon: $ICON_FILE -> ${PKG_NAME}.svg (hicolor)"
      ;;
    *)
      echo "WARNING: Unsupported icon extension: $ICON_FILE (expected .png or .svg). Skipping icon install."
      ;;
  esac
else
  echo "WARNING: No icon file found."
  echo "Put an icon in the project root as 'it4home.png' or 'icon.png' (or set ICON_FILE=path/to/icon.png) and rebuild."
fi

echo "[7/7] Building .deb with fpm..."
OUT_DEB="${PKG_NAME}_${VERSION}_${ARCH}.deb"

POSTINST="${BUILD_DIR}/postinst_${PKG_NAME}.sh"
mkdir -p "$BUILD_DIR"
cat > "$POSTINST" <<'POST'
#!/usr/bin/env bash
set -e

# Refresh icon caches (best-effort; commands may or may not exist on minimal systems)
if command -v update-icon-caches >/dev/null 2>&1; then
  update-icon-caches /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

# Refresh desktop file MIME cache (only needed if you ship MimeType= entries)
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
fi

# Some menus react to this (safe if present)
if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi
POST
chmod 0755 "$POSTINST"

fpm -s dir -t deb   -n "${PKG_NAME}"   -v "${VERSION}"   -a "${ARCH}"   --description "${DESC}"   --url "${URL}"   --maintainer "${MAINT}"   --after-install "$POSTINST"   -d "python3"   -d "python3-tk"   -d "xdg-utils"   -C "$STAGE"   -p "$OUT_DEB"   .

echo
echo "Built: ${PROJECT_DIR}/${OUT_DEB}"
