#!/usr/bin/env bash
# install_launchd.sh - install/remove a macOS LaunchAgent to start the dev servers at login
# Usage: ./scripts/install_launchd.sh install|uninstall|status

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
PLIST_NAME="com.2026-orion.dashboard.plist"
PLIST_PATH="$LAUNCH_DIR/$PLIST_NAME"
RUN_SCRIPT="$ROOT_DIR/scripts/run_dev.sh"

install() {
  mkdir -p "$LAUNCH_DIR"
  cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.2026-orion.dashboard</string>
    <key>ProgramArguments</key>
    <array>
      <string>$RUN_SCRIPT</string>
      <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$ROOT_DIR/logs/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT_DIR/logs/launchd.stderr.log</string>
    <key>WorkingDirectory</key>
    <string>$ROOT_DIR</string>
  </dict>
</plist>
PLIST
  echo "Plist created at $PLIST_PATH"
  echo "Loading LaunchAgent..."
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  launchctl load "$PLIST_PATH"
  echo "Installed and loaded LaunchAgent. It will run the dev servers at login (and now)."
}

uninstall() {
  echo "Unloading LaunchAgent if present..."
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  if [ -f "$PLIST_PATH" ]; then
    rm -f "$PLIST_PATH"
    echo "Removed $PLIST_PATH"
  else
    echo "No LaunchAgent plist found to remove"
  fi
}

status() {
  if [ -f "$PLIST_PATH" ]; then
    echo "LaunchAgent installed at $PLIST_PATH"
  else
    echo "LaunchAgent not installed"
  fi
}

case "${1:-}" in
  install)
    install
    ;;
  uninstall)
    uninstall
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 {install|uninstall|status}"
    exit 2
    ;;
esac
