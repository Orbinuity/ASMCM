#!/bin/sh
set -e

BINARY_NAME="asmcm"
APP_NAME="ASMCM"
UNINSTALLER_VERSION="1.1.0-posix"
LOCAL_BIN="$HOME/.local/bin/$BINARY_NAME"
DESKTOP_FILE="$HOME/.local/share/applications/asmcm.desktop"
MIME_FILE="$HOME/.local/share/mime/packages/asmcm.xml"
MAC_APP_DIR="$HOME/Applications/ASMCM.app"

printf "\n\033[1m=== %s Uninstaller v%s ===\033[0m\n\n" "$APP_NAME" "$UNINSTALLER_VERSION"

REMOVED=0

# Clean up binary
if [ -f "$LOCAL_BIN" ]; then
    rm -f "$LOCAL_BIN"
    REMOVED=1
fi

# Clean up Linux associations
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    REMOVED=1
fi

if [ -f "$MIME_FILE" ]; then
    rm -f "$MIME_FILE"
    if command -v update-mime-database >/dev/null 2>&1; then
        update-mime-database "$HOME/.local/share/mime" >/dev/null 2>&1 || true
    fi
    REMOVED=1
fi

# Clean up macOS application bundle
if [ -d "$MAC_APP_DIR" ]; then
    rm -rf "$MAC_APP_DIR"
    LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    if [ -f "$LSREGISTER" ]; then
        "$LSREGISTER" -u "$MAC_APP_DIR" >/dev/null 2>&1 || true
    fi
    REMOVED=1
fi

if [ "$REMOVED" -eq 1 ]; then
    printf "\033[0;32m[✓]\033[0m %s and file associations removed.\n" "$APP_NAME"
else
    printf "\033[1;33m[!]\033[0m %s installation was not found.\n" "$APP_NAME"
fi