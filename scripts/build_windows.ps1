[CmdletBinding()]
param(
    [string]$Version = "0.8.1",
    [string]$BuildPython = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($BuildPython) {
    (Resolve-Path $BuildPython).Path
} else {
    Join-Path $projectRoot ".venv\Scripts\python.exe"
}
$pythonDirectory = Split-Path -Parent $python
$pyinstaller = Join-Path $pythonDirectory "pyinstaller.exe"
$icon = Join-Path $projectRoot "icon\logo.ico"
$ffmpeg = Join-Path $projectRoot "vendor\ffmpeg\bin\ffmpeg.exe"
$ffprobe = Join-Path $projectRoot "vendor\ffmpeg\bin\ffprobe.exe"
$deno = Join-Path $projectRoot "vendor\deno\deno.exe"
$distRoot = Join-Path $projectRoot "dist"
$buildRoot = Join-Path $projectRoot "build"
$releaseRoot = Join-Path $projectRoot "releases\v$Version"
$preparedRoot = Join-Path $releaseRoot "prepared"
$assetRoot = Join-Path $releaseRoot "assets"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python de build não encontrado: $python"
}
if (-not (Test-Path -LiteralPath $pyinstaller)) {
    throw "PyInstaller não encontrado. Instale-o conscientemente com: .\.venv\Scripts\python.exe -m pip install pyinstaller"
}
if (-not (Test-Path -LiteralPath $icon)) {
    throw "Ícone do aplicativo não encontrado em icon\logo.ico."
}
foreach ($tool in @($ffmpeg, $ffprobe, $deno)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Ferramenta local não encontrada: $tool. Execute scripts\setup_tools.ps1 antes do build."
    }
}
if (Test-Path -LiteralPath $releaseRoot) {
    throw "A pasta de release já existe: $releaseRoot. Remova-a manualmente se quiser gerar novamente."
}

New-Item -ItemType Directory -Force -Path $releaseRoot, $preparedRoot, $assetRoot | Out-Null

function Invoke-PyInstaller {
    param(
        [string]$Name,
        [string]$EntryPoint,
        [switch]$WithIcon,
        [switch]$OneFile,
        [switch]$IncludeYtDlp,
        [switch]$IncludeMediaTools
    )

    $bundleMode = if ($OneFile) { "--onefile" } else { "--onedir" }
    $arguments = @(
        "--noconfirm",
        "--clean",
        $bundleMode,
        "--windowed",
        "--name", $Name,
        "--distpath", $distRoot,
        "--workpath", (Join-Path $buildRoot $Name),
        "--specpath", (Join-Path $buildRoot "spec"),
        "--paths", $projectRoot
    )
    if ($WithIcon) {
        $arguments += @("--icon", $icon, "--add-data", "$projectRoot\icon;icon")
    }
    if ($IncludeYtDlp) {
        $arguments += @(
            "--collect-all", "yt_dlp",
            "--collect-all", "yt_dlp_ejs",
            "--copy-metadata", "yt-dlp",
            "--copy-metadata", "yt-dlp-ejs"
        )
    }
    if ($IncludeMediaTools) {
        $arguments += @(
            "--add-binary", "$ffmpeg;vendor/ffmpeg/bin",
            "--add-binary", "$ffprobe;vendor/ffmpeg/bin",
            "--add-binary", "$deno;vendor/deno"
        )
    }
    $arguments += $EntryPoint
    $previousPath = $env:PATH
    $cleanPath = ($previousPath -split [IO.Path]::PathSeparator | Where-Object {
        $_ -and
        -not (Test-Path -LiteralPath (Join-Path $_ "icuuc.dll")) -and
        -not (Test-Path -LiteralPath (Join-Path $_ "icudt*.dll"))
    }) -join [IO.Path]::PathSeparator
    $env:PATH = $cleanPath
    try {
        & $pyinstaller @arguments
        $pyinstallerExitCode = $LASTEXITCODE
    }
    finally {
        $env:PATH = $previousPath
    }
    if ($pyinstallerExitCode -ne 0) {
        throw "PyInstaller falhou para $Name (código $pyinstallerExitCode)."
    }
}

Invoke-PyInstaller -Name "Tuberino Downloader" -EntryPoint (Join-Path $projectRoot "app\__main__.py") -WithIcon -OneFile -IncludeYtDlp -IncludeMediaTools
Invoke-PyInstaller -Name "Tuberino Downloader Updater" -EntryPoint (Join-Path $projectRoot "app\update_helper.py") -OneFile

$mainExecutable = Join-Path $distRoot "Tuberino Downloader.exe"
$updaterExecutable = Join-Path $distRoot "Tuberino Downloader Updater.exe"
if (-not (Test-Path -LiteralPath $mainExecutable) -or -not (Test-Path -LiteralPath $updaterExecutable)) {
    throw "Os dois executáveis esperados não foram gerados em dist."
}

Copy-Item -LiteralPath $mainExecutable -Destination $preparedRoot
Copy-Item -LiteralPath $updaterExecutable -Destination $preparedRoot
New-Item -ItemType Directory -Force -Path (Join-Path $preparedRoot "Output") | Out-Null

Push-Location $projectRoot
$previousPythonPath = $env:PYTHONPATH
if ($previousPythonPath) {
    $env:PYTHONPATH = "$projectRoot;$previousPythonPath"
} else {
    $env:PYTHONPATH = $projectRoot
}
try {
    & $python (Join-Path $projectRoot "scripts\build_update.py") `
        --source $preparedRoot `
        --version $Version `
        --output $assetRoot
    $buildUpdateExitCode = $LASTEXITCODE
}
finally {
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $previousPythonPath
    }
    Pop-Location
}
if ($buildUpdateExitCode -ne 0) {
    throw "A criação dos assets do updater falhou (código $buildUpdateExitCode)."
}

Write-Host "Release preparada em: $releaseRoot"
