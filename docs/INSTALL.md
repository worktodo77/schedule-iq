# Installing ScheduleIQ

## Analysts (Windows — recommended)

1. Download `ScheduleIQ-<version>-windows.zip` from the repository's Releases
   page (built automatically by CI from tagged commits — never install ad-hoc
   builds; see GOVERNANCE.md §4).
2. Extract anywhere (e.g., `C:\Tools\ScheduleIQ`).  No admin rights needed.
3. Run `ScheduleIQ.exe`.  Optional: right-click → Pin to Start.

The bundle includes Python, the Qt GUI, matplotlib/openpyxl, MPXJ with a Java
runtime (native .mpp reading), and the LI report template.  PDF output uses
your installed Microsoft Word; without Word the tool still produces the .docx
and tells you.

## Developers (source)

```bash
git clone <repo>
cd schedule-iq
pip install -e .[gui,dev]        # extras: [mpp] native .mpp, [pdf] Word PDF
pytest
scheduleiq gui
```

`[mpp]` requires a Java 8+ runtime on PATH (the mpxj package bridges to it).

## Building the Windows bundle locally

```powershell
pip install .[gui,mpp,pdf,dev]
pyinstaller installer/scheduleiq.spec
# output: dist/ScheduleIQ/  → zip and distribute
```

CI (`.github/workflows/build.yml`) performs exactly these steps on a Windows
runner for every version tag and attaches the zip to the GitHub release.
