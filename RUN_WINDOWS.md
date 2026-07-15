# Run ScheduleIQ on Windows

ScheduleIQ v0.4.8 includes a native PySide6 desktop workspace. Analysis runs
locally; schedule files are not uploaded by the application.

## Install from source

Prerequisites: Windows 10/11 and Python 3.10 or newer. Microsoft Word is needed
only when **Create PDF via Microsoft Word** is enabled.

```powershell
git clone https://github.com/worktodo77/schedule-iq.git
Set-Location schedule-iq
py -m pip install -e .
scheduleiq gui
```

The equivalent module launch is:

```powershell
py -m scheduleiq.cli gui
```

Open the demo series with `tests/fixtures/demo_baseline.xer`,
`demo_update1.xer`, and `demo_update2.xer`, then select **Run analysis**.

## Run the packaged application (no Python required)

Tagged releases attach `ScheduleIQ-vX.Y.Z-windows.zip` to the GitHub release and
also publish the same ZIP as the workflow artifact. Download and extract the
entire ZIP, then run:

```text
ScheduleIQ\ScheduleIQ.exe
```

Keep the extracted `_internal` folder beside `ScheduleIQ.exe`; it contains the
Qt runtime, platform plugin, governed matrix/scorecard, and report template.
Windows may show a first-run SmartScreen prompt until the executable is code
signed.

## Build the packaged application locally

```powershell
py -m pip install -e .[mpp,pdf,dev]
py -m PyInstaller --clean installer/scheduleiq.spec
$env:QT_QPA_PLATFORM = "offscreen"
& dist\ScheduleIQ\ScheduleIQ.exe --smoke-test
& dist\ScheduleIQ\ScheduleIQ.exe --demo-smoke tests\fixtures\demo_baseline.xer packaged-smoke-output
& dist\ScheduleIQ\ScheduleIQ.exe
```

The folder bundle is written to `dist\ScheduleIQ`. Distribute the whole folder,
not the executable by itself.

## Expected first-run workflow

1. Add or drag one or more `.xer`, `.xml`, or `.mpp` files.
2. Confirm automatic data-date ordering and any warnings.
3. Choose Series or Benchmark mode; configure optional CSV overlays in Settings.
4. Run the analysis and review Report Card, Checks, Trends, Paths, and Forensics.
5. Use **Open output** to reach the Word/PDF, workbooks, figures, and cockpit.

The `INTERNAL_PRIVILEGED` workbook remains opt-in, weight-0, privileged work
product and is explicitly labeled **not for a counterparty** in the application.
