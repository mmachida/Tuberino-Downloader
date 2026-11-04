[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$vendorRoot = Join-Path $repoRoot 'vendor'
$ffmpegRoot = Join-Path $vendorRoot 'ffmpeg'
$denoRoot = Join-Path $vendorRoot 'deno'

$ffmpegRelease = 'autobuild-2026-10-25-13-00'
$ffmpegAsset = 'ffmpeg-N-128094-g31855b2a70-win64-lgpl.zip'
$ffmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$ffmpegRelease/$ffmpegAsset"
$ffmpegChecksumsUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$ffmpegRelease/checksums.sha256"
$ffmpegSha256 = '3addaa7353e759b9e19f8419db4f6ec755eeeb625e60c0c3519c398fcc80d364'

$denoVersion = '2.9.8'
$denoAsset = 'deno-x86_64-pc-windows-msvc.zip'
$denoUrl = "https://github.com/denoland/deno/releases/download/v$denoVersion/$denoAsset"
$denoChecksumUrl = "$denoUrl.sha256sum"
$denoSha256 = 'cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927ed d93bf'.Replace(' ', '')

function Get-FileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-Checksum {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected,
        [Parameter(Mandatory)][string]$Label
    )
    $actual = Get-FileSha256 -Path $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "Checksum SHA-256 inválido para $Label. Esperado: $Expected; obtido: $actual."
    }
}

function Invoke-VerifiedDownload {
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][string]$ExpectedSha256,
        [Parameter(Mandatory)][string]$Label
    )
    if ((Test-Path -LiteralPath $Destination) -and -not $Force) {
        throw "O arquivo $Destination já existe. Use -Force somente se deseja substituí-lo."
    }
    Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination
    Assert-Checksum -Path $Destination -Expected $ExpectedSha256 -Label $Label
}

function Assert-PublishedFfmpegChecksum {
    param([Parameter(Mandatory)][string]$ChecksumFile)
    $line = Get-Content -Raw -LiteralPath $ChecksumFile
    $match = [regex]::Match($line, "(?m)^([0-9a-fA-F]{64})\s+$([regex]::Escape($ffmpegAsset))\s*$")
    if (-not $match.Success) {
        throw "O checksum publicado para $ffmpegAsset não foi encontrado."
    }
    if ($match.Groups[1].Value.ToLowerInvariant() -ne $ffmpegSha256) {
        throw 'O checksum embutido do FFmpeg não coincide com o manifesto oficial baixado.'
    }
}

function Assert-PublishedDenoChecksum {
    param([Parameter(Mandatory)][string]$ChecksumFile)
    $text = Get-Content -Raw -LiteralPath $ChecksumFile
    $match = [regex]::Match($text, '(?im)^Hash\s*:\s*([0-9a-f]{64})\s*$')
    if (-not $match.Success -or $match.Groups[1].Value.ToLowerInvariant() -ne $denoSha256) {
        throw 'O checksum embutido do Deno não coincide com o manifesto oficial baixado.'
    }
}

function Assert-ToolVersion {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Arguments,
        [Parameter(Mandatory)][string]$Label
    )
    $output = & $Path $Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Não foi possível validar $Label em $Path."
    }
    Write-Host "${Label}: $($output -join ' ')"
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("downloaderino-tools-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    New-Item -ItemType Directory -Path $vendorRoot -Force | Out-Null
    if (((Test-Path -LiteralPath $ffmpegRoot) -or (Test-Path -LiteralPath $denoRoot)) -and -not $Force) {
        throw 'Uma instalação local já existe em vendor. Use -Force somente após confirmar a substituição.'
    }

    $ffmpegZip = Join-Path $tempRoot $ffmpegAsset
    $ffmpegChecksums = Join-Path $tempRoot 'ffmpeg-checksums.sha256'
    Invoke-WebRequest -UseBasicParsing -Uri $ffmpegChecksumsUrl -OutFile $ffmpegChecksums
    Assert-PublishedFfmpegChecksum -ChecksumFile $ffmpegChecksums
    Invoke-WebRequest -UseBasicParsing -Uri $ffmpegUrl -OutFile $ffmpegZip
    Assert-Checksum -Path $ffmpegZip -Expected $ffmpegSha256 -Label 'FFmpeg'

    $denoZip = Join-Path $tempRoot $denoAsset
    $denoChecksum = Join-Path $tempRoot "$denoAsset.sha256sum"
    Invoke-WebRequest -UseBasicParsing -Uri $denoChecksumUrl -OutFile $denoChecksum
    Assert-PublishedDenoChecksum -ChecksumFile $denoChecksum
    Invoke-WebRequest -UseBasicParsing -Uri $denoUrl -OutFile $denoZip
    Assert-Checksum -Path $denoZip -Expected $denoSha256 -Label 'Deno'

    $ffmpegExtracted = Join-Path $tempRoot 'ffmpeg-extracted'
    Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $ffmpegExtracted
    $ffmpegExe = Get-ChildItem -LiteralPath $ffmpegExtracted -Filter 'ffmpeg.exe' -File -Recurse | Select-Object -First 1
    $ffprobeExe = Get-ChildItem -LiteralPath $ffmpegExtracted -Filter 'ffprobe.exe' -File -Recurse | Select-Object -First 1
    if ($null -eq $ffmpegExe -or $null -eq $ffprobeExe) {
        throw 'O arquivo do FFmpeg não contém ffmpeg.exe e ffprobe.exe.'
    }

    $denoExtracted = Join-Path $tempRoot 'deno-extracted'
    Expand-Archive -LiteralPath $denoZip -DestinationPath $denoExtracted
    $denoExe = Get-ChildItem -LiteralPath $denoExtracted -Filter 'deno.exe' -File -Recurse | Select-Object -First 1
    if ($null -eq $denoExe) {
        throw 'O arquivo do Deno não contém deno.exe.'
    }

    if ($Force) {
        Remove-Item -LiteralPath $ffmpegRoot, $denoRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    $ffmpegBin = Join-Path $ffmpegRoot 'bin'
    New-Item -ItemType Directory -Path $ffmpegBin, $denoRoot -Force | Out-Null
    Copy-Item -LiteralPath $ffmpegExe.FullName -Destination (Join-Path $ffmpegBin 'ffmpeg.exe')
    Copy-Item -LiteralPath $ffprobeExe.FullName -Destination (Join-Path $ffmpegBin 'ffprobe.exe')
    Copy-Item -LiteralPath $denoExe.FullName -Destination (Join-Path $denoRoot 'deno.exe')

    Assert-ToolVersion -Path (Join-Path $ffmpegBin 'ffmpeg.exe') -Arguments '-version' -Label 'FFmpeg'
    Assert-ToolVersion -Path (Join-Path $ffmpegBin 'ffprobe.exe') -Arguments '-version' -Label 'FFprobe'
    Assert-ToolVersion -Path (Join-Path $denoRoot 'deno.exe') -Arguments '--version' -Label 'Deno'
    Write-Host 'Ferramentas provisionadas e verificadas em vendor.'
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}

