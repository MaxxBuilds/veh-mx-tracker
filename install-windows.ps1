param(
    [switch]$Build,
    [switch]$NoDesktopShortcut,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$AppName = "Veh Mx Tracker"
$AppId = "veh-mx-tracker"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
$RoamingAppData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $HOME "AppData\Roaming" }
$InstallDir = Join-Path $LocalAppData "Programs\$AppName"
$InstalledExe = Join-Path $InstallDir "$AppName.exe"
$DistExe = Join-Path $Root "dist\$AppName.exe"
$FlatExe = Join-Path $Root "$AppName.exe"
$StartMenuDir = Join-Path $RoamingAppData "Microsoft\Windows\Start Menu\Programs"
$StartMenuShortcut = Join-Path $StartMenuDir "$AppName.lnk"
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$DesktopShortcut = if ($DesktopDir) { Join-Path $DesktopDir "$AppName.lnk" } else { $null }

function New-AppShortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory
    )
    $Parent = Split-Path -Parent $ShortcutPath
    if ($Parent) {
        New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    }
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetPath
    $Shortcut.WorkingDirectory = $WorkingDirectory
    $Shortcut.IconLocation = "$TargetPath,0"
    $Shortcut.Description = "Vehicle maintenance tracker"
    $Shortcut.Save()
}

if ($Uninstall) {
    Remove-Item -LiteralPath $StartMenuShortcut -Force -ErrorAction SilentlyContinue
    if ($DesktopShortcut) {
        Remove-Item -LiteralPath $DesktopShortcut -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Removed $AppName installed app files and shortcuts."
    Write-Host "Saved app data remains in: $LocalAppData\$AppId"
    exit 0
}

function Get-SourceExe {
    if (Test-Path -LiteralPath $DistExe) {
        return $DistExe
    }
    if (Test-Path -LiteralPath $FlatExe) {
        return $FlatExe
    }
    return $null
}

if (-not (Get-SourceExe)) {
    if ($Build) {
        & (Join-Path $Root "build-windows.ps1")
    } else {
        throw "Missing $AppName.exe. Download and extract the Windows artifact from GitHub Actions, or run .\install-windows.ps1 -Build from the source folder."
    }
}

$SourceExe = Get-SourceExe
if (-not $SourceExe) {
    throw "Build finished, but $AppName.exe was not found."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -LiteralPath $SourceExe -Destination $InstalledExe -Force
New-AppShortcut -ShortcutPath $StartMenuShortcut -TargetPath $InstalledExe -WorkingDirectory $InstallDir
if (-not $NoDesktopShortcut -and $DesktopShortcut) {
    New-AppShortcut -ShortcutPath $DesktopShortcut -TargetPath $InstalledExe -WorkingDirectory $InstallDir
}

Write-Host "Installed $AppName to: $InstallDir"
Write-Host "Start Menu shortcut: $StartMenuShortcut"
if (-not $NoDesktopShortcut -and $DesktopShortcut) {
    Write-Host "Desktop shortcut: $DesktopShortcut"
}
Write-Host "Saved app data location: $LocalAppData\$AppId"
