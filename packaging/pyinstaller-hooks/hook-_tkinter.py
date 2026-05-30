from pathlib import Path
import sys

py_root = Path(sys.base_prefix)
tcl_dir = py_root / "tcl" / "tcl8.6"
tk_dir = py_root / "tcl" / "tk8.6"
dll_dir = py_root / "DLLs"

datas = []
if tcl_dir.exists():
    datas.append((str(tcl_dir), "_tcl_data"))
if tk_dir.exists():
    datas.append((str(tk_dir), "_tk_data"))

binaries = []
for dll_name in ("tcl86t.dll", "tk86t.dll"):
    dll_path = dll_dir / dll_name
    if dll_path.exists():
        binaries.append((str(dll_path), "."))
