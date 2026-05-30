# Veh Mx Tracker

Veh Mx Tracker is a desktop app for tracking vehicle maintenance, parts, suppliers, shop work, labor hours, and costs. It runs on Linux from source and can be packaged as a Windows x64 executable. It works with vehicles that have a VIN and vehicles that only have a reg number.

All saved records are stored locally on the computer. Saved NHTSA information for each vehicle is cached locally after it is fetched, including decoded vehicle info, recalls, complaints, and available TSB model matches. Selected vehicles can show their last saved NHTSA report offline, and when internet is available the app refreshes and re-saves the NHTSA info after the vehicle is selected.

## Features

- Save an unlimited number of vehicles, limited only by available local storage.
- Add a vehicle by VIN.
- Add a vehicle by Reg Number without a VIN.
- Add or edit a VIN later.
- Edit saved vehicle info later, including Reg Number, VIN, year, make, model, trim, engine, and body/class.
- Search saved vehicles by VIN, Reg Number, year, make, model, trim, engine, or body.
- Decode VINs using free public NHTSA data.
- Check public NHTSA TSB model availability, recall data, and complaint data.
- Save, edit, and delete dated vehicle notes.
- Save, edit, and delete Vehicle MX records.
- Save, edit, and delete Other Work records that are not tied to a vehicle.
- Save blank or partial notes/work records when needed.
- Track parts, vendor/source, direct cost, labor hours, mileage, equipment hours, and next due date.
- View all parts ever recorded for a selected vehicle.
- Save custom Suppliers/Sources separately from vehicles.
- Store supplier/source website, point of contact, role, email, phone, address/location, and notes.
- Edit, delete, view, and open saved Suppliers/Sources later.
- Store and edit user profile info: name, rank, and labor cost per hour.
- Prompt for profile info on startup when profile fields are empty.
- Show total labor hours, labor value, direct costs, and grand total for the full profile.
- Show totals for a selected vehicle.
- Filter totals and exports by optional date range.
- Export one clear `.txt` report.
- Dashboard tab for due/overdue service, highest-cost vehicles, cost by category, most-used parts, and recurring issue trends.
- Backup tab for one-click database backup and restore.
- Quick Guide button for self-explanatory in-app instructions.
- Clear all saved information after warnings, optional export prompt, and final `DELETE` confirmation.

## One-command install

These commands install dependencies, download the current GitHub source archive, refresh the app folder, and run the installer. They reuse `~/Desktop/MaxxBuilds`.

### Linux Mint / Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y curl tar python3 python3-tk && REPO=veh-mx-tracker && URL=https://github.com/MaxxBuilds/veh-mx-tracker/archive/refs/heads/main.tar.gz && BASE="$HOME/Desktop/MaxxBuilds" && DEST="$BASE/$REPO" && TMP="$(mktemp -d)" && mkdir -p "$BASE" "$DEST" && curl -L "$URL" -o "$TMP/app.tar.gz" && tar -xzf "$TMP/app.tar.gz" -C "$TMP" && SRC="$TMP/veh-mx-tracker-main" && cp -a "$SRC"/. "$DEST"/ && rm -rf "$DEST/__pycache__" && chmod +x "$DEST/install.sh" && "$DEST/install.sh" && rm -rf "$TMP"
```

### Fedora

```bash
sudo dnf install -y curl tar python3 python3-tkinter && REPO=veh-mx-tracker && URL=https://github.com/MaxxBuilds/veh-mx-tracker/archive/refs/heads/main.tar.gz && BASE="$HOME/Desktop/MaxxBuilds" && DEST="$BASE/$REPO" && TMP="$(mktemp -d)" && mkdir -p "$BASE" "$DEST" && curl -L "$URL" -o "$TMP/app.tar.gz" && tar -xzf "$TMP/app.tar.gz" -C "$TMP" && SRC="$TMP/veh-mx-tracker-main" && cp -a "$SRC"/. "$DEST"/ && rm -rf "$DEST/__pycache__" && chmod +x "$DEST/install.sh" && "$DEST/install.sh" && rm -rf "$TMP"
```

### Arch Linux / Manjaro

```bash
sudo pacman -Sy --noconfirm curl tar python tk && REPO=veh-mx-tracker && URL=https://github.com/MaxxBuilds/veh-mx-tracker/archive/refs/heads/main.tar.gz && BASE="$HOME/Desktop/MaxxBuilds" && DEST="$BASE/$REPO" && TMP="$(mktemp -d)" && mkdir -p "$BASE" "$DEST" && curl -L "$URL" -o "$TMP/app.tar.gz" && tar -xzf "$TMP/app.tar.gz" -C "$TMP" && SRC="$TMP/veh-mx-tracker-main" && cp -a "$SRC"/. "$DEST"/ && rm -rf "$DEST/__pycache__" && chmod +x "$DEST/install.sh" && "$DEST/install.sh" && rm -rf "$TMP"
```

### openSUSE

```bash
sudo zypper --non-interactive refresh && sudo zypper --non-interactive install curl tar python3 python3-tk && REPO=veh-mx-tracker && URL=https://github.com/MaxxBuilds/veh-mx-tracker/archive/refs/heads/main.tar.gz && BASE="$HOME/Desktop/MaxxBuilds" && DEST="$BASE/$REPO" && TMP="$(mktemp -d)" && mkdir -p "$BASE" "$DEST" && curl -L "$URL" -o "$TMP/app.tar.gz" && tar -xzf "$TMP/app.tar.gz" -C "$TMP" && SRC="$TMP/veh-mx-tracker-main" && cp -a "$SRC"/. "$DEST"/ && rm -rf "$DEST/__pycache__" && chmod +x "$DEST/install.sh" && "$DEST/install.sh" && rm -rf "$TMP"
```

## Windows x64 install and build

Windows builds use PyInstaller to package the Python/Tkinter app as one executable with the app icon embedded.

### Install the Windows artifact

1. Open the repository **Actions** tab.
2. Open the latest successful **Windows build** run.
3. Download the `Veh-Mx-Tracker-Windows-x64` artifact.
4. Extract the ZIP file.
5. Run `Veh Mx Tracker.exe`, or install shortcuts from the extracted/source folder with PowerShell:

```powershell
.\install-windows.ps1
```

The Windows installer copies the executable to the current user's local Programs folder and creates Start Menu and desktop shortcuts. To skip the desktop shortcut, run:

```powershell
.\install-windows.ps1 -NoDesktopShortcut
```

To remove the installed executable and shortcuts later, run:

```powershell
.\install-windows.ps1 -Uninstall
```

### Build on Windows

Install Python 3.12 x64 from python.org, then run this from the project folder in PowerShell:

```powershell
.\build-windows.ps1
```

If PowerShell blocks local scripts on your computer, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
```

The executable is created at:

```text
dist\Veh Mx Tracker.exe
```

You can build and install in one step from the source folder with:

```powershell
.\install-windows.ps1 -Build
```

### GitHub Actions build

The repository includes `.github/workflows/windows-build.yml`. The workflow builds `dist\Veh Mx Tracker.exe` on a Windows x64 runner and uploads it as an artifact named `Veh-Mx-Tracker-Windows-x64`.

Run it manually from the repository's **Actions** tab, or let it run when the app or Windows packaging files change.

## User instructions

### Autosave

Records are saved as they are added or edited. When the app closes, it also autosaves the selected vehicle, search text, font size, panel widths, and last-used app state so the next launch can pick back up more easily. The app opens fullscreen by default.


### Start the app

Veh Mx Tracker opens fullscreen by default. Press `F11` to toggle fullscreen. Press `Esc` to close the app and autosave.

After installing, open **Veh Mx Tracker** from the desktop launcher, or run:

```bash
veh-mx-tracker
```

From the project folder, you can also run:

```bash
python3 ./veh_mx_tracker.py
```

### Fill out profile info

On first launch, the app prompts for profile info if anything is empty.

Use **Edit Profile** at the top to update:

- Name
- Rank
- Labor cost per hour

Labor cost is used to calculate labor value in totals and exports.

### Add a vehicle by VIN

1. Enter a 17-character VIN in the VIN box.
2. Click **Decode VIN**.
3. Review the decoded vehicle info.
4. Click **Save Vehicle**.
5. Enter a Reg Number if you want one.

### Add a vehicle without a VIN

1. Click **Save Vehicle by Reg Number**.
2. Enter the Reg Number and any known vehicle details.
3. Click OK.

The vehicle will be saved as a no-VIN vehicle. You can add a VIN later.

### Edit saved vehicle info

1. Select the vehicle from **Saved Vehicles**.
2. Click **Edit Vehicle Info**.
3. Update Reg Number, VIN, year, make, model, trim, engine, or body/class.
4. Click OK.

If you add a valid VIN, the app tries to fill missing vehicle info from public NHTSA data. You can still manually enter or correct vehicle details.

### Saved vehicle public info

When a saved VIN vehicle is selected, the app immediately shows the locally saved NHTSA information if available, then refreshes online when internet is available. The refreshed data is saved locally again and includes decoded VIN information, public NHTSA TSB model matches, recalls, and complaints. No-VIN vehicles show the manually saved vehicle information.

### Font size and settings

Use the **A+** and **A-** buttons at the top to change app-wide font size. Open the **Settings** tab for font controls, color theme, fullscreen startup, NHTSA URL settings, auto-refresh behavior, and saved app settings.

### Search vehicles

Use the search box above **Saved Vehicles** to search by:

- VIN
- Reg Number
- Year
- Make
- Model
- Trim
- Engine
- Body/class

Click **Clear** to show all saved vehicles again. Double-click or press Enter on supported lists and search results to open or edit the selected item.

### Add notes

1. Select a saved vehicle.
2. Open the **Notes** tab.
3. Click **Add Dated Note**.
4. Enter the note and click OK.

Use **Edit Selected Note** or **Delete Selected Note** to manage saved notes.

### Add Vehicle MX records

1. Select a saved vehicle.
2. Open the **Vehicle MX** tab.
3. Click **Add Maintenance Record**.
4. Enter any known fields, such as service date, mileage, hours, category, description, parts, vendor/source, cost, labor hours, and next due date.
5. Click OK.

Vehicle MX records can be edited or deleted later.

### View all parts for a vehicle

1. Select a saved vehicle.
2. Open the **Vehicle MX** tab.
3. Click **Show Vehicle Parts History**.

The app shows all recorded parts for that selected vehicle, including dates, vendor/source, costs, and related work descriptions.

### Add Other Work records

Use **Other Work** for shop/fleet/mechanic work that is not tied to one vehicle.

1. Open the **Other Work** tab.
2. Click **Add Unlinked Work**.
3. Enter any known details.
4. Click OK.

Other Work records can be edited or deleted later.

### Add Suppliers/Sources

Suppliers/Sources are standalone records. They are not linked to vehicles.

1. Open the **Suppliers/Sources** tab.
2. Click **Add Supplier/Source**.
3. Enter any supplier/source info:
   - Supplier/source name
   - Website URL
   - Point of contact
   - Contact role
   - Email address
   - Phone number
   - Address/location
   - Notes
4. Click OK.

Use:

- **Edit Supplier/Source** to change saved supplier/source info.
- **Delete Supplier/Source** to remove one.
- **View Supplier/Source Details** to see all saved contact info.
- **Open Website** to open the saved website URL.

### Dashboard and trends

Open the **Dashboard** tab and click **Refresh Dashboard / Trends** to see:

- Due/overdue service
- Highest-cost vehicles
- Cost by category
- Most-used parts
- Recurring issues/categories
- Total labor and cost summary

Click **Show Overdue / Due Now** to view due-service details in the main report area.

### Backup and restore

Open the **Backup** tab to make a local copy of the app database or restore from a saved backup. Restore creates a safety copy before replacing current data.

### View totals

Click **Profile / Totals** at the top.

You can enter optional start and end dates in `YYYY-MM-DD` format.

Totals include:

- Total records
- Labor hours
- Labor value
- Direct costs
- Grand total

The report shows both profile-wide totals and selected-vehicle totals when a vehicle is selected.

### Export records

Click **Export TXT**.

You can enter an optional date range, then choose where to save the report. The folder chooser defaults to `~/Desktop/MaxxBuilds/veh-mx-tracker/veh-mx-exports` in this local checkout, but you can pick any folder.

The app creates one clear `.txt` report sorted by vehicle. The report includes:

- Profile info
- Total labor/cost summary
- Saved vehicles
- Vehicle MX records
- Notes
- Other Work records
- Suppliers/Sources

### Clear all saved information

Click **Clear ALL Saved Info** only when you want to wipe the app data.

The app will:

1. Show a warning.
2. Offer a chance to export first.
3. Show a final warning.
4. Require typing `DELETE` before clearing.

Clear-all deletes:

- Vehicles
- Notes
- Vehicle MX records
- Other Work records
- Suppliers/Sources
- Profile information

## Data storage

Saved data is stored locally in the current user's app-owned data folder.

Linux:

```text
~/.config/veh-mx-tracker/vehicles.sqlite3
```

Windows:

```text
%LOCALAPPDATA%\veh-mx-tracker\vehicles.sqlite3
```

On Windows, if an older `%USERPROFILE%\.config\veh-mx-tracker` folder exists and the native app-data folder has not been created yet, the app copies the older data into the native app-data folder on startup.

Exports default to:

```text
Linux:   ~/Desktop/MaxxBuilds/veh-mx-tracker/veh-mx-exports
Windows: %USERPROFILE%\Documents\MaxxBuilds\veh-mx-tracker\veh-mx-exports
```

The user can still choose a different folder each time they export.

## Offline use

Saved vehicles, notes, Vehicle MX records, Other Work records, Suppliers/Sources, profile info, and the last saved public vehicle info are available locally. If the computer is offline, selecting a saved vehicle shows the locally cached NHTSA info from the last successful online fetch.

## Internet use

The app uses the internet only when the user decodes/checks a VIN through free public NHTSA sources:

- NHTSA vPIC VIN decoder API
- NHTSA recalls API
- NHTSA complaints API

Supplier/source websites open only when the user chooses **Open Website**. Supplier/source URLs are saved as standalone links and are not vehicle-specific.

## Install

From this folder:

```bash
./install.sh
```

If Python/Tkinter dependencies are missing and package installation is approved:

```bash
./install.sh --install-deps
```

### Desktop launcher troubleshooting

If the desktop says the launcher is not executable or not trusted, run:

```bash
chmod +x "$HOME/Desktop/Veh Mx Tracker.desktop"
chmod +x "$HOME/.local/bin/veh-mx-tracker"
gio set "$HOME/Desktop/Veh Mx Tracker.desktop" metadata::trusted true 2>/dev/null || true
```

Then right-click the desktop launcher and choose **Allow Launching** if your desktop shows that option.

You can always start the app from Terminal with:

```bash
veh-mx-tracker
```

## Updating from GitHub

On Linux, run the same copy/paste install command again. It downloads the current GitHub source archive, refreshes `~/Desktop/MaxxBuilds/veh-mx-tracker`, and reinstalls the app files. On Windows, download the latest successful Windows build artifact and run `install-windows.ps1` again from the extracted folder. Saved database, settings, and exports live in the app-owned data locations listed above.

## Uninstall

Linux:

```bash
./uninstall.sh
```

Windows:

```powershell
.\install-windows.ps1 -Uninstall
```

Linux uninstall removes the installed app files, launchers, icons, and saved app database/settings. If exports exist, uninstall copies them to a desktop folder named `Old Veh Mx Tracker Exports` before removing app-created data. Windows uninstall removes the installed executable and shortcuts. Saved Windows app data remains in `%LOCALAPPDATA%\veh-mx-tracker`.

## Installed files

Linux:

```text
~/.local/share/veh-mx-tracker/veh_mx_tracker.py
~/.local/bin/veh-mx-tracker
~/.local/share/applications/veh-mx-tracker.desktop
~/.local/share/icons/veh-mx-tracker.png
~/Desktop/Veh Mx Tracker.desktop
```

Windows:

```text
%LOCALAPPDATA%\Programs\Veh Mx Tracker\Veh Mx Tracker.exe
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Veh Mx Tracker.lnk
%USERPROFILE%\Desktop\Veh Mx Tracker.lnk
```

## Project files

```text
veh_mx_tracker.py      Main Python/Tkinter app
README.md              User instructions and project info
install.sh             Current-user installer/updater
uninstall.sh           Full uninstaller wrapper
veh-mx-tracker.png     App icon
veh-mx-tracker.ico     Windows app icon
build-windows.ps1      Windows x64 build script
install-windows.ps1    Windows current-user installer/uninstaller
Veh Mx Tracker.spec    PyInstaller build spec
```

## License

Code is released under the MIT License. See `LICENSE`.
