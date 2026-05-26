#!/usr/bin/env bash
set -euo pipefail
APP_ID="veh-mx-tracker"
APP_NAME="Veh Mx Tracker"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APPDIR="$HOME/.local/share/$APP_ID"
BINDIR="$HOME/.local/bin"
ICONDIR="$HOME/.local/share/icons"
APPDESKTOPDIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APPDESKTOPDIR/$APP_ID.desktop"
BIN_FILE="$BINDIR/$APP_ID"
ICON_FILE="$ICONDIR/$APP_ID.png"
CONFIGDIR="$HOME/.config/$APP_ID"
CREATE_DESKTOP=1; UNINSTALL=0; INSTALL_DEPS=0
usage(){ cat <<'EOF'
Veh Mx Tracker installer
Usage: ./install.sh [--install-deps] [--no-desktop] [--uninstall]
EOF
}
while [ $# -gt 0 ]; do case "$1" in --install-deps) INSTALL_DEPS=1;; --no-desktop) CREATE_DESKTOP=0;; --uninstall) UNINSTALL=1;; -h|--help) usage; exit 0;; *) echo "Unknown option: $1" >&2; usage >&2; exit 1;; esac; shift; done
find_desktop_dir(){ if command -v xdg-user-dir >/dev/null 2>&1; then xdg-user-dir DESKTOP 2>/dev/null || true; else printf '%s\n' "$HOME/Desktop"; fi; }
trust_desktop_file(){
  f="$1"
  chmod 755 "$f" 2>/dev/null || true
  if command -v gio >/dev/null 2>&1; then
    gio set "$f" metadata::trusted true >/dev/null 2>&1 || true
    gio set -t string "$f" metadata::trusted true >/dev/null 2>&1 || true
  fi
}
if [ "$UNINSTALL" -eq 1 ]; then
  DDIR="$(find_desktop_dir)"
  EXPORT_DEST="${DDIR:-$HOME/Desktop}/Old Veh Mx Tracker Exports"
  stamp=""
  preserve_exports() {
    src="$1"
    [ -d "$src" ] || return 0
    find "$src" -mindepth 1 -print -quit | grep -q . || return 0
    if [ -z "$stamp" ]; then
      stamp="$(date +%Y%m%d-%H%M%S)"
      mkdir -p "$EXPORT_DEST/$stamp"
    fi
    cp -a "$src/." "$EXPORT_DEST/$stamp/"
  }
  preserve_exports "$APPDIR/veh-mx-exports"
  preserve_exports "$CONFIGDIR/veh-mx-exports"
  if [ -n "$stamp" ]; then echo "Moved saved exports to: $EXPORT_DEST/$stamp"; fi
  rm -rf "$APPDIR" "$CONFIGDIR"
  rm -f "$BIN_FILE" "$DESKTOP_FILE" "$ICON_FILE"
  [ -n "$DDIR" ] && rm -f "$DDIR/$APP_NAME.desktop" 2>/dev/null || true
  echo "Removed $APP_NAME app files and saved app data for user: ${USER:-unknown}. Saved exports were preserved if present."; exit 0
fi
if [ "$INSTALL_DEPS" -eq 1 ]; then
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get update; sudo apt-get install -y python3 python3-tk;
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y python3 python3-tkinter;
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -Sy --noconfirm python tk;
  elif command -v zypper >/dev/null 2>&1; then sudo zypper --non-interactive install python3 python3-tk;
  else echo "No supported package manager found. Install Python 3 and Tkinter manually."; fi
fi
command -v python3 >/dev/null 2>&1 || { echo "python3 is required." >&2; exit 1; }
python3 - <<'PY' >/dev/null 2>&1 || { echo "Python Tkinter is required. Rerun with --install-deps or install python3-tk." >&2; exit 1; }
import tkinter
PY
mkdir -p "$APPDIR" "$BINDIR" "$ICONDIR" "$APPDESKTOPDIR"
cp -f "$SRC_DIR/veh_mx_tracker.py" "$APPDIR/veh_mx_tracker.py"
cp -f "$SRC_DIR/veh-mx-tracker.png" "$ICON_FILE"
chmod 755 "$APPDIR/veh_mx_tracker.py"; chmod 644 "$ICON_FILE"
cat > "$BIN_FILE" <<EOF
#!/usr/bin/env sh
exec /usr/bin/env python3 "$APPDIR/veh_mx_tracker.py" "\$@"
EOF
chmod 755 "$BIN_FILE"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Vehicle maintenance tracker
Exec=$BIN_FILE
TryExec=$BIN_FILE
Icon=$ICON_FILE
Terminal=false
Categories=Utility;Automotive;
StartupNotify=true
NoDisplay=false
EOF
trust_desktop_file "$DESKTOP_FILE"
if [ "$CREATE_DESKTOP" -eq 1 ]; then
  DDIR="$(find_desktop_dir)"
  if [ -n "$DDIR" ]; then
    mkdir -p "$DDIR"
    cp -f "$DESKTOP_FILE" "$DDIR/$APP_NAME.desktop"
    trust_desktop_file "$DDIR/$APP_NAME.desktop"
    if command -v xdg-desktop-icon >/dev/null 2>&1; then
      xdg-desktop-icon install --novendor "$DDIR/$APP_NAME.desktop" >/dev/null 2>&1 || true
      trust_desktop_file "$DDIR/$APP_NAME.desktop"
    fi
  fi
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPDESKTOPDIR" >/dev/null 2>&1 || true
[ -x "$BIN_FILE" ] || { echo "Install failed: launcher is not executable: $BIN_FILE" >&2; exit 1; }
[ -x "$DESKTOP_FILE" ] || { echo "Install failed: desktop entry is not executable: $DESKTOP_FILE" >&2; exit 1; }
echo "Installed $APP_NAME for user: ${USER:-unknown}"
echo "Run it with: $APP_ID"
if [ "$CREATE_DESKTOP" -eq 1 ]; then
  echo "Desktop launcher: $(find_desktop_dir)/$APP_NAME.desktop"
  echo "If your desktop asks, right-click the launcher and choose Allow Launching."
else
  echo "Desktop launcher skipped because --no-desktop was used."
fi
