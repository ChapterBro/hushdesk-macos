## Build failure (Phase 1)
- Command: `PYINSTALLER_BIN=.venv_build/bin/pyinstaller DESKTOP_ALIAS=0 ./scripts/build`
- Error: `FileExistsError` when PyInstaller tries to symlink Qt framework resources under `dist/HushDesk/_internal/PySide6/Qt/lib/Qt3DAnimation.framework/Resources`.
- Cause: `HushDesk.spec` calls `collect_all('PySide6')`, which duplicates Qt framework symlinks already provided by the built-in PyInstaller hook for PySide6 6.10. Removing the redundant `collect_all` resolves the clash.
- Fix plan: update `HushDesk.spec` to drop the explicit `collect_all('PySide6')` call and rely on the hook.
- Additional fix: remove `--collect-all PySide6` from `scripts/build` to avoid duplicate Qt framework symlinks created by newer PyInstaller hooks.
## CLI launch failure: dataclass slots
- Command: `NSUnbufferedIO=YES dist/HushDesk.app/Contents/MacOS/HushDesk`
- Error: `TypeError: dataclass() got an unexpected keyword argument 'slots'`
- Cause: Build used system Python 3.9; project relies on Python 3.10+ dataclass features.
- Fix: Recreated `.venv_build` with Homebrew `python3.11`, reinstalled PyInstaller/PySide6, rebuilt app.

## CLI launch failure: missing hushdesk.ui.evidence_panel
- Cause: SyntaxError prevented `evidence_panel` from compiling under Python 3.11 due to f-string with backslash.
- Fix: Sanitized f-string to pre-escape double quotes before formatting.
## CLI launch failure: missing bundle resources
- Command: `NSUnbufferedIO=YES dist/HushDesk.app/Contents/MacOS/HushDesk`
- Error: `FileNotFoundError` for `hushdesk/config/building_master_mac.json` once bundled.
- Fix: Introduced `hushdesk._paths.resource_path` to resolve data files inside PyInstaller bundles and updated `id.rooms.load_building_master` to use it.

## Close event runtime error
- Symptom: Finder run spammed `Internal C++ object (PySide6.QtCore.QThread) already deleted` on shutdown.
- Fix: Hardened `MainWindow.closeEvent` to guard against already-disposed worker threads.
