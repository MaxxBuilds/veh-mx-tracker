def pre_find_module_path(hook_api):
    # Keep tkinter discoverable. Some Windows Python layouts run Tkinter
    # correctly but fail PyInstaller's isolated Tcl/Tk probe.
    return
