# PyInstaller spec — ScheduleIQ Windows bundle.
# Build:  pyinstaller installer/scheduleiq.spec   (from the repo root)
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "assets", "LI_report_base.docx"), "assets"),
    (os.path.join(ROOT, "src", "scheduleiq", "metrics", "matrix.yaml"),
     "scheduleiq/metrics"),
]
binaries = []
hiddenimports = ["scheduleiq.metrics.checks.core"]

# MPXJ (optional): bundle the jar + jpype if installed so .mpp works offline.
try:
    import mpxj  # noqa: F401
    datas += collect_data_files("mpxj")
    binaries += collect_dynamic_libs("jpype")
    hiddenimports += ["jpype", "mpxj"]
except ImportError:
    pass

a = Analysis(
    [os.path.join(ROOT, "src", "scheduleiq", "gui", "app.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ScheduleIQ",
    console=False,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="ScheduleIQ")
