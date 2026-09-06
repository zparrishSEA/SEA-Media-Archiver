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

# 4. Launch the application
open "$DEST_PATH"