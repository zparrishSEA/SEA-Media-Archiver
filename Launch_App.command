#!/bin/bash
cd "$(dirname "$0")"

APP_NAME="SEA Media Archiver.app"
DEST_PATH="/Applications/$APP_NAME"

# 1. Remove any old version of the app from the Applications folder
rm -rf "$DEST_PATH"

# 2. Move the newly downloaded app bundle to Applications
mv "$APP_NAME" /Applications/

# 3. Remove the Apple quarantine flag from the new location
xattr -cr "$DEST_PATH"

# 4. Display an instruction message to the user
osascript -e 'display dialog "Please grant Full Disk Access to SEA Media Archiver so it can save your media.\n\nAfter you click OK, System Settings will open. Please toggle the switch next to the app, then restart it." buttons {"OK"} default button "OK" with title "Permission Required" with icon caution'

# 5. Open the Full Disk Access settings window for the user
open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"

# 6. Launch the application
open "$DEST_PATH"