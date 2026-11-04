# Tuberino Downloader

![Version](https://img.shields.io/badge/version-v0.8.3-1769aa)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2B-0078d4)
![License](https://img.shields.io/badge/license-MIT-2ea44f)

Tuberino Downloader is an open-source Windows desktop application for
analyzing and downloading authorized public media from YouTube, Twitch,
Twitter/X and Instagram. It also extracts audio to MP3. The application uses
PySide6, the Python API of [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), and
FFmpeg for media processing.

The interface supports English and Brazilian Portuguese, with Night and Day
themes. Network, analysis, download and conversion work runs outside the Qt UI
thread so the window remains responsive.

## Features

- YouTube videos, multiple individual video URLs and playlists.
- Per-item selection, removal, unavailable-item detection and sequential queue.
- YouTube playlist thumbnail limit to avoid thousands of image requests.
- Twitch VOD and Clip downloads.
- Public Twitter/X video downloads.
- Public Instagram posts, reels, TV videos and stories when no authentication
  is required by the extractor.
- Real quality and container choices derived from source metadata.
- Original container, `Compatible MP4 H.264` when available, or explicit MP4
  conversion with FFmpeg.
- Audio-only MP3 extraction at 128, 192 or 320 kbps.
- Per-item download, merge, conversion and validation progress.
- English/Portuguese localization, Night/Day themes and Windows always-on-top.
- GitHub Releases update checking with release notes, SHA-256 verification and
  a hidden Windows update helper.

## Requirements

- Windows 10 or newer, x64 recommended.
- Python 3.12, 3.13 or 3.14 for source development.
- FFmpeg and FFprobe for merging, MP3 extraction and explicit MP4 conversion.
- Deno and `yt-dlp-ejs` for current YouTube JavaScript support.

The application can use validated tools in `vendor/` or executables available
on `PATH`. The repository does not include FFmpeg, FFprobe or Deno binaries.

## Run from source

Open PowerShell in the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m app
```

`run.bat` starts the application from `.venv` after the environment has been
installed. It does not install dependencies automatically.

The project also supports Python 3.13 and 3.14. Use the same interpreter for
creating `.venv`, installing dependencies and starting the application.

## Media tools

Run the explicit provisioning script when you want local FFmpeg/Deno tools:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_tools.ps1
```

The script downloads only the configured tool archives, verifies their SHA-256
values and places the executables under `vendor/`. Review the script and the
licenses of each third-party distribution before redistributing binaries.

Manual installation is also supported: install FFmpeg/FFprobe and Deno from
their official sources and make them available on `PATH`.

## Using the application

1. Open a platform tab.
2. Choose the content type when the platform offers more than one type.
3. Paste a public URL and select **Add**.
4. Select the items to process.
5. Choose Video or MP3 and select only the output options relevant to that
   mode.
6. Choose the destination and click **Download**.

The default destination is `Output/` next to the executable in a frozen
Windows distribution, or in the project directory when running from source.
A different existing folder is remembered in Settings. If it is removed, the
application falls back to the default `Output/` folder.

Use **File > Open folder** to open the current destination. The application
does not overwrite existing media silently and validates final files before
reporting success.

## Local data and privacy

Runtime logs are written to `logs/log.txt` and contain generic date/time and
failure information only. Settings are stored in the Windows application data
directory. Output files, logs, temporary files, credentials, cookies and
signed media URLs are local and are not part of the public source tree.

Tuberino Downloader does not bypass DRM or access controls, does not implement
login/cookie import and does not send analytics to a project server. Use it
only for media you own or are authorized to download.

## GitHub Releases updater

The updater checks stable releases in
[`mmachida/Tuberino-Downloader`](https://github.com/mmachida/Tuberino-Downloader),
ignores drafts/prereleases and selects the highest numeric tag newer than the
installed version.

A Windows x64 release must publish these assets:

```text
tuberino-downloader-windows-x64.zip
tuberino-downloader-windows-x64.sha256
```

The ZIP must contain `update-manifest.json` at its root. The manifest lists
only managed application files. The updater downloads and validates the ZIP in
a temporary directory outside the installation folder, verifies SHA-256 and
safe paths, preserves unknown files and user data, shows the GitHub release
body as the changelog, and restarts the application without opening a command
prompt. If the new application cannot start, the previous files are restored.

To build the updater assets from a prepared Windows distribution:

```powershell
python scripts/build_update.py `
  --source path\to\prepared-distribution `
  --version 0.8.3 `
  --output releases
```

The packaging script excludes `.git`, development caches, `/delete/`,
`/docs/`, `/logs/`, `/Output/`, `/releases/`, credentials, partial downloads
and media generated during development.

To build the Windows distribution itself, install PyInstaller in the selected
build environment and run:

```powershell
python -m pip install pyinstaller
.\scripts\build_windows.ps1 -Version 0.8.3
```

The script accepts `-BuildPython` when the build interpreter is different from
the project environment. Python 3.12 is a good compatibility choice for
PyInstaller/PySide6 builds on Windows:

```powershell
.\scripts\build_windows.ps1 `
  -Version 0.8.3 `
  -BuildPython C:\path\to\python312\python.exe
```

The resulting `releases\v<version>\assets` directory contains the ZIP and its
SHA-256 file. Third-party FFmpeg/Deno binaries are intentionally not committed
to the source repository. The Windows build embeds them in the main executable,
so the end-user ZIP does not require a separate installation; follow the
vendors' redistribution terms before publishing that binary release.
The main application is packaged as a single Windows executable; the separate
updater executable is kept alongside it so it can replace the main executable
after the application closes.
The distributable ZIP contains the two executables, an empty `Output\` folder
for first use, and the technical `update-manifest.json` required by the updater.

## Development validation

Run these checks in the project environment:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

Automated tests are offline and use mocks/fixtures. Online analysis and
downloads must use content that the tester is authorized to access. A site can
change its extractor, restrict a format or require authentication after a
release; those limitations should be reported instead of bypassed.

## Project layout

```text
app/                 application source
icon/                application icon and language flag assets
scripts/             tool setup and release packaging helpers
vendor/README.md     local third-party tool layout and license notes
LICENSE              MIT license
pyproject.toml       Python metadata and dependencies
run.bat              Windows source launcher
```

Internal development tests, experiments and generated release artifacts are
kept outside the public source package in this workspace.

## License

The Tuberino Downloader source is released under the [MIT License](LICENSE).
PySide6, yt-dlp/yt-dlp-ejs, FFmpeg and Deno retain their own licenses and
notices. Check the official projects before redistributing their binaries.

## Links

- GitHub: https://github.com/mmachida/Tuberino-Downloader
- Support: https://ko-fi.com/mmachida
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- PySide6: https://doc.qt.io/qtforpython-6/
- FFmpeg builds: https://github.com/yt-dlp/FFmpeg-Builds
