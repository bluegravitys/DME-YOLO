# EXE Packaging Guide

This project can be packaged as a Windows executable with `PyInstaller`.

## Recommended mode

Use `--onedir` first. This mode is more stable for projects that bundle:

- `torch`
- `ultralytics`
- local YOLO `.pt` weights
- static website assets

## Build command

Open PowerShell in the project root:

```powershell
.\build_exe.ps1
```

The build script automatically reads the current Windows system proxy and converts it to a pip-friendly proxy URL.
This means it can work more reliably when Clash rule mode is enabled.

Windowed build without a console:

```powershell
.\build_exe.ps1 -Windowed
```

Single-file build:

```powershell
.\build_exe.ps1 -OneFile
```

Single-file windowed build:

```powershell
.\build_exe.ps1 -OneFile -Windowed
```

## Output paths

Default recommended build:

```text
dist\PCBDefectStudio\PCBDefectStudio.exe
```

One-file build:

```text
dist\PCBDefectStudio.exe
```

## Runtime behavior

- The packaged app starts a local FastAPI service.
- It opens the browser automatically.
- The bundled EXE includes:
  - `best.pt`
  - `classes.txt`
  - `templates/`
  - `static/`
  - built-in example PCB images

## Notes

- `-OneFile` is convenient, but startup may be slower because the package needs to unpack first.
- If you replace `best.pt`, rebuild the EXE so the new weights are bundled.
- If you want a custom icon later, it can be added to `build_exe.ps1`.
- For normal pip usage with Clash enabled, you can use:

```powershell
.\pip_with_clash.ps1 install pyinstaller
```
