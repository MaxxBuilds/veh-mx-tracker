$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv-windows"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Spec = Join-Path $Root "Veh Mx Tracker.spec"

Set-Location $Root

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Test-BuildPython {
    param([string]$Command)

    try {
        $Result = & $Command -c "import platform, sys; print(f'{sys.version_info.major}.{sys.version_info.minor};{platform.architecture()[0]}')" 2>$null
        return $Result -eq "3.12;64bit"
    } catch {
        return $false
    }
}

$BuildPython = $env:PYTHON
if (-not $BuildPython) {
    foreach ($Candidate in @("py", "python")) {
        if (Get-Command $Candidate -ErrorAction SilentlyContinue) {
            if ($Candidate -eq "py") {
                try {
                    $Probe = & py -3.12-64 -c "import platform, sys; print(f'{sys.version_info.major}.{sys.version_info.minor};{platform.architecture()[0]}')" 2>$null
                    if ($Probe -eq "3.12;64bit") {
                        $BuildPython = "py -3.12-64"
                        break
                    }
                } catch {}
            } elseif (Test-BuildPython $Candidate) {
                $BuildPython = $Candidate
                break
            }
        }
    }
}

if (-not $BuildPython) {
    throw "Python 3.12 x64 is required. Install it from https://www.python.org/downloads/windows/ and try again."
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    if ($BuildPython -eq "py -3.12-64") {
        Invoke-Checked "Create virtual environment" { py -3.12-64 -m venv $Venv }
    } else {
        Invoke-Checked "Create virtual environment" { & $BuildPython -m venv $Venv }
    }
}

Invoke-Checked "Upgrade pip" { & $VenvPython -m pip install --upgrade pip }
Invoke-Checked "Install Windows build dependencies" { & $VenvPython -m pip install -r (Join-Path $Root "requirements-windows-build.txt") }
Invoke-Checked "Build Windows executable" { & $VenvPython -m PyInstaller --noconfirm --clean $Spec }

$Exe = Join-Path $Root "dist\Veh Mx Tracker.exe"
if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Build finished, but $Exe was not created."
}

Write-Host ""
Write-Host "Windows x64 build created:"
Write-Host $Exe
