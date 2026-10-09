#!/bin/sh
set -e

REPO="Orbinuity/ASMCM"
APP_NAME="ASMCM"
BINARY_NAME="asmcm"
INSTALL_DIR="$HOME/.local/bin"
INSTALLER_VERSION="1.2.1-posix"
ASSETS_URL="https://raw.githubusercontent.com/${REPO}/main/assets"

BOLD=$(printf '\033[1m')
GREEN=$(printf '\033[0;32m')
CYAN=$(printf '\033[0;36m')
YELLOW=$(printf '\033[1;33m')
RED=$(printf '\033[0;31m')
NC=$(printf '\033[0m')

info()    { printf "%s[*]%s %s\n" "$CYAN" "$NC" "$1"; }
success() { printf "%s[✓]%s %s\n" "$GREEN" "$NC" "$1"; }
warn()    { printf "%s[!]%s %s\n" "$YELLOW" "$NC" "$1"; }
error()   { printf "%s[✗]%s %s\n" "$RED" "$NC" "$1"; exit 1; }

printf "\n%s=== %s installer v%s ===%s\n\n" "$BOLD" "$APP_NAME" "$INSTALLER_VERSION" "$NC"

info "Fetching latest release info from GitHub..."
LATEST_RELEASE_JSON=$(curl -s "https://api.github.com/repos/${REPO}/releases/latest") || error "Failed to connect to GitHub."
LATEST_TAG=$(echo "$LATEST_RELEASE_JSON" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST_TAG" ]; then
    error "Could not retrieve latest version tag from GitHub API."
fi

TARGET_BINARY="$INSTALL_DIR/$BINARY_NAME"

OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_ASSET="linux";;
    Darwin*)    OS_ASSET="macos";;
    *)          error "Unsupported Operating System: ${OS}";;
esac

DOWNLOAD_URL=$(echo "$LATEST_RELEASE_JSON" \
  | grep "browser_download_url" \
  | grep "${OS_ASSET}" \
  | cut -d '"' -f 4 \
  | head -n 1)

if [ -z "$DOWNLOAD_URL" ]; then
    error "No binary release found matching platform: ${OS_ASSET}"
fi

mkdir -p "$INSTALL_DIR"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

info "Downloading ${APP_NAME} ${LATEST_TAG}..."
curl -fL -o "$TMP_DIR/$BINARY_NAME" "$DOWNLOAD_URL"
chmod +x "$TMP_DIR/$BINARY_NAME"

mv "$TMP_DIR/$BINARY_NAME" "$TARGET_BINARY"
success "Successfully installed ${APP_NAME} (${LATEST_TAG}) to ${INSTALL_DIR}"

# --- Linux File Associations, Wayland Icons, and Desktop Launcher ---
if [ "$OS_ASSET" = "linux" ]; then
    info "Setting up app launcher, icons, and file associations for Linux/Wayland..."
    DESKTOP_DIR="$HOME/.local/share/applications"
    MIME_DIR="$HOME/.local/share/mime/packages"
    ICON_APP_DIR="$HOME/.local/share/icons/hicolor/64x64/apps"
    ICON_MIME_DIR="$HOME/.local/share/icons/hicolor/64x64/mimetypes"
    
    mkdir -p "$DESKTOP_DIR" "$MIME_DIR" "$ICON_APP_DIR" "$ICON_MIME_DIR"

    curl -sL "$ASSETS_URL/app.png" -o "$ICON_APP_DIR/asmcm.png" || true
    curl -sL "$ASSETS_URL/asmc.png" -o "$ICON_MIME_DIR/application-x-asmc.png" || true
    curl -sL "$ASSETS_URL/asmcx.png" -o "$ICON_MIME_DIR/application-x-asmcx.png" || true

    cat <<EOF > "$MIME_DIR/asmcm.xml"
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-asmc">
    <comment>ASMC Source File</comment>
    <icon name="application-x-asmc"/>
    <glob pattern="*.asmc"/>
  </mime-type>
  <mime-type type="application/x-asmcx">
    <comment>ASMC Executable File</comment>
    <icon name="application-x-asmcx"/>
    <glob pattern="*.asmcx"/>
  </mime-type>
</mime-info>
EOF

    cat <<EOF > "$DESKTOP_DIR/asmcm.desktop"
[Desktop Entry]
Type=Application
Name=ASMCM
Exec=$TARGET_BINARY %f
Icon=asmcm
Terminal=false
StartupWMClass=asmcm
MimeType=application/x-asmc;application/x-asmcx;
Categories=Development;Utility;
EOF

    # Refresh Linux desktop and icon databases for Wayland compositors
    if command -v update-mime-database >/dev/null 2>&1; then
        update-mime-database "$HOME/.local/share/mime" >/dev/null 2>&1 || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    fi
    if command -v xdg-mime >/dev/null 2>&1; then
        xdg-mime default asmcm.desktop application/x-asmc application/x-asmcx >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
    fi
    touch "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

    success "App launcher, file associations, and icons configured."
fi

# --- macOS Application Bundle and Icons ---
if [ "$OS_ASSET" = "macos" ]; then
    info "Setting up icons and App handler for macOS..."
    MAC_APP_DIR="$HOME/Applications/ASMCM.app"
    mkdir -p "$MAC_APP_DIR/Contents/MacOS" "$MAC_APP_DIR/Contents/Resources"

    curl -sL "$ASSETS_URL/app.icns" -o "$MAC_APP_DIR/Contents/Resources/app.icns" || true
    curl -sL "$ASSETS_URL/asmc.icns" -o "$MAC_APP_DIR/Contents/Resources/asmc.icns" || true
    curl -sL "$ASSETS_URL/asmcx.icns" -o "$MAC_APP_DIR/Contents/Resources/asmcx.icns" || true

    cat <<EOF > "$MAC_APP_DIR/Contents/MacOS/ASMCM"
#!/bin/sh
exec "$TARGET_BINARY" "\$@"
EOF
    chmod +x "$MAC_APP_DIR/Contents/MacOS/ASMCM"

    cat <<EOF > "$MAC_APP_DIR/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>ASMCM</string>
    <key>CFBundleIconFile</key>
    <string>app.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.orbinuity.asmcm</string>
    <key>CFBundleName</key>
    <string>ASMCM</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>asmc</string>
            </array>
            <key>CFBundleTypeIconFile</key>
            <string>asmc.icns</string>
            <key>CFBundleTypeName</key>
            <string>ASMC Source File</string>
            <key>CFBundleTypeRole</key>
            <string>Editor</string>
        </dict>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>asmcx</string>
            </array>
            <key>CFBundleTypeIconFile</key>
            <string>asmcx.icns</string>
            <key>CFBundleTypeName</key>
            <string>ASMC Executable File</string>
            <key>CFBundleTypeRole</key>
            <string>Viewer</string>
        </dict>
    </array>
</dict>
</plist>
EOF

    LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    if [ -f "$LSREGISTER" ]; then
        "$LSREGISTER" -f "$MAC_APP_DIR" >/dev/null 2>&1 || true
    fi
    success "Registered macOS App Handler & icons."
fi

case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *) 
    warn "${INSTALL_DIR} is not in your PATH."
    info "Add it to your shell config (~/.bashrc or ~/.zshrc):"
    printf "    %sexport PATH=\"\$HOME/.local/bin:\$PATH\"%s\n" "$BOLD" "$NC"
    ;;
esac

printf "\n%s%sDone! Run '%s' to launch.%s\n\n" "$GREEN" "$BOLD" "$BINARY_NAME" "$NC"