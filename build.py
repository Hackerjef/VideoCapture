from cx_Freeze import setup, Executable

build_exe_options = {"excludes": ["lib2to3"], "include_msvcr": True, "optimize": 1}

setup(
    name="dev.nadie.dcontrol",
    version="0.1", description="hmm",
    options={"build_exe": build_exe_options},
    executables=[Executable("main.py")],
)
