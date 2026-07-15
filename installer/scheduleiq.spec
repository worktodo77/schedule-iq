# PyInstaller spec — ScheduleIQ Windows folder bundle.
# Build from repository root: python -m PyInstaller --clean installer/scheduleiq.spec
import os

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PACKAGE = os.path.join(ROOT, "src", "scheduleiq")

datas = [
    (os.path.join(ROOT, "assets", "LI_report_base.docx"), "assets"),
    (os.path.join(PACKAGE, "metrics", "matrix.yaml"), "scheduleiq/metrics"),
    (os.path.join(PACKAGE, "scorecard.yaml"), "scheduleiq"),
    (os.path.join(PACKAGE, "gui", "assets", "scheduleiq_icon.svg"),
     "scheduleiq/gui/assets"),
    (os.path.join(PACKAGE, "gui", "assets", "scheduleiq_icon.png"),
     "scheduleiq/gui/assets"),
]

# runner.py intentionally imports additive analytics/report modules lazily so a
# failed optional surface cannot sink a normal run. Bundle those modules even
# though static analysis cannot see every import edge.
hiddenimports = collect_submodules("scheduleiq")

# MPXJ / JPype are optional. When installed by the tagged Windows workflow,
# their normal PyInstaller hooks collect the jar, JVM bridge, and binaries.
a = Analysis(
    [os.path.join(ROOT, "installer", "launch_gui.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScheduleIQ",
    console=False,
    icon=os.path.join(PACKAGE, "gui", "assets", "scheduleiq_icon.png"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ScheduleIQ",
)
