# Manifest

Files included in this release:

```text
README.md                              User instructions and project info
LICENSE                                MIT license and asset note
.gitignore                             Git ignore rules
DEPENDENCIES.md                        Runtime and build dependency notes
MANIFEST.md                            This file
install.sh                             Linux current-user installer/updater
uninstall.sh                           Linux uninstaller wrapper
build-windows.ps1                      Windows x64 build script
install-windows.ps1                    Windows current-user installer/uninstaller
requirements-windows-build.txt         Windows build dependency list
Veh Mx Tracker.spec                    PyInstaller build spec
.github/workflows/windows-build.yml    GitHub Actions Windows build workflow
packaging/pyinstaller-hooks/           PyInstaller Tkinter hook files
veh_mx_tracker.py                      Main Python/Tkinter app
veh-mx-tracker.png                     Linux app icon
veh-mx-tracker.ico                     Windows app icon
```

Linux installed user files:

```text
~/.local/share/veh-mx-tracker/veh_mx_tracker.py
~/.local/bin/veh-mx-tracker
~/.local/share/applications/veh-mx-tracker.desktop
~/.local/share/icons/veh-mx-tracker.png
~/Desktop/Veh Mx Tracker.desktop
```

Windows installed user files:

```text
%LOCALAPPDATA%\Programs\Veh Mx Tracker\Veh Mx Tracker.exe
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Veh Mx Tracker.lnk
%USERPROFILE%\Desktop\Veh Mx Tracker.lnk
```

Runtime user data:

```text
Linux:   ~/.config/veh-mx-tracker/vehicles.sqlite3
Windows: %LOCALAPPDATA%\veh-mx-tracker\vehicles.sqlite3
```
