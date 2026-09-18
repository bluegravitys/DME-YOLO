# Windows environment setup

This project is intended to run on Windows with Python 3.10 and a fresh virtual environment.

## Recommended setup

GPU mode:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1 -Mode gpu
```

CPU mode:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1 -Mode cpu
```

After setup:

```powershell
.\.venv\Scripts\Activate.ps1
.\run_app.ps1
```

## What the setup script does

1. Downloads and installs Python 3.10.11 if it is missing.
2. Detects and backs up a broken existing `.venv`.
3. Creates a new virtual environment.
4. Installs PyTorch, project dependencies, and the local `ultralytics` package.
5. Verifies that the key imports work.

## Notes

- `gpu` mode installs CUDA 12.8 PyTorch wheels.
- `cpu` mode installs CPU-only PyTorch wheels.
- The old `.venv` in this repository is broken because it points to a missing Python 3.10 installation.
