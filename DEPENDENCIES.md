# Dependencies

Veh Mx Tracker is a Python 3 / Tkinter desktop app.

Required:

- Python 3
- Tkinter for Python 3
- Standard Python libraries used by the app:
  - sqlite3
  - tkinter
  - urllib
  - json
  - pathlib
  - threading
  - shutil

Optional:

- Internet access for live NHTSA VIN decode, recalls, complaints, and TSB model-match refreshes.

The app stores its local database in:

```text
~/.config/veh-mx-tracker/vehicles.sqlite3
```
