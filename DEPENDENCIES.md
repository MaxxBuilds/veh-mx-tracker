# Dependencies

Veh Mx Tracker is a Python 3 / Tkinter desktop app.

Linux runtime requirements:

- Python 3
- Tkinter for Python 3

Windows runtime options:

- Use the Windows x64 executable artifact from GitHub Actions, or
- Build locally with Python 3.12 x64 and PyInstaller through `build-windows.ps1`.

Standard Python libraries used by the app:

- sqlite3
- tkinter
- urllib
- json
- pathlib
- threading
- shutil
- os

Windows build dependency:

- PyInstaller, pinned in `requirements-windows-build.txt`

Optional:

- Internet access for live NHTSA VIN decode, recalls, complaints, and TSB model-match refreshes.

The app stores its local database in the current user's app-owned data folder:

```text
Linux:   ~/.config/veh-mx-tracker/vehicles.sqlite3
Windows: %LOCALAPPDATA%\veh-mx-tracker\vehicles.sqlite3
```
