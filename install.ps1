$ErrorActionPreference = "Stop"

$Repo = "Orbinuity/ASMCM"
$AppId = "asmcm"
$AppName = "ASMCM"
$BinaryName = "$AppId.exe"
$InstallDir = "$env:LOCALAPPDATA\Programs\$AppName"
$TargetBinary = "$InstallDir\$BinaryName"
$AssetsDir = "$InstallDir\assets"
$InstallerVersion = "1.2.0-windows"
$AssetsUrl = "https://raw.githubusercontent.com/$Repo/main/assets"

function Write-Header ($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Success ($msg) { Write-Host "[✓] $msg" -ForegroundColor Green }
function Write-Info ($msg)    { Write-Host "[*] $msg" -ForegroundColor DarkCyan }
function Write-Warn ($msg)    { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err ($msg)     { Write-Host "[✗] $msg" -ForegroundColor Red; exit 1 }

Write-Header "$AppName installer v$InstallerVersion"

Write-Info "Checking GitHub for the latest release..."
try {
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "PowerShell" }
    $LatestTag =$Release.tag_name
} catch {
    Write-Err "Failed to reach GitHub API: $_"
}

$Asset =$Release.assets | Where-Object { $_.name -like "*windows*" -or $_.name -like "*.exe" } | Select-Object -First 1

if (-not $Asset) {
    Write-Err "No Windows executable found in release $LatestTag"
}

Write-Info "Downloading $AppName$LatestTag..."
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}
if (-not (Test-Path $AssetsDir)) {
    New-Item -ItemType Directory -Force -Path $AssetsDir | Out-Null
}

try {
    Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile$TargetBinary
    Write-Success "Binary successfully saved to $InstallDir"
} catch {
    Write-Err "Failed to download binary: $_"
}

# Download Icons
Write-Info "Downloading file and application icons..."
try {
    Invoke-WebRequest -Uri "$AssetsUrl/app.ico" -OutFile "$AssetsDir\app.ico" -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri "$AssetsUrl/asmc.ico" -OutFile "$AssetsDir\asmc.ico" -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri "$AssetsUrl/asmcx.ico" -OutFile "$AssetsDir\asmcx.ico" -ErrorAction SilentlyContinue
} catch {}

# Register PATH
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$InstallDir*") {
    Write-Info "Adding $InstallDir to User PATH..."
    $NewPath = "$UserPath;$InstallDir"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    Write-Warn "PATH updated. Restart open terminals for changes to take effect."
}

# Register Registry Entries & Icons
Write-Info "Registering .asmc and .asmcx file associations and icons..."
try {
    # .asmc file association
    New-Item -Path "HKCU:\Software\Classes\.asmc" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\.asmc" -Name "(Default)" -Value "ASMCM.AsmcFile" | Out-Null
    
    New-Item -Path "HKCU:\Software\Classes\ASMCM.AsmcFile\DefaultIcon" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\ASMCM.AsmcFile\DefaultIcon" -Name "(Default)" -Value "$AssetsDir\asmc.ico" | Out-Null
    
    New-Item -Path "HKCU:\Software\Classes\ASMCM.AsmcFile\shell\open\command" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\ASMCM.AsmcFile" -Name "(Default)" -Value "ASMC Source File" | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\ASMCM.AsmcFile\shell\open\command" -Name "(Default)" -Value """$TargetBinary"" ""%1""" | Out-Null

    # .asmcx file association
    New-Item -Path "HKCU:\Software\Classes\.asmcx" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\.asmcx" -Name "(Default)" -Value "ASMCM.AsmcxFile" | Out-Null
    
    New-Item -Path "HKCU:\Software\Classes\ASMCM.AsmcxFile\DefaultIcon" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\ASMCM.AsmcxFile\DefaultIcon" -Name "(Default)" -Value "$AssetsDir\asmcx.ico" | Out-Null
    
    New-Item -Path "HKCU:\Software\Classes\ASMCM.AsmcxFile\shell\open\command" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\ASMCM.AsmcxFile" -Name "(Default)" -Value "ASMC Executable File" | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\ASMCM.AsmcxFile\shell\open\command" -Name "(Default)" -Value """$TargetBinary"" ""%1""" | Out-Null

    # Refresh Windows Shell Icon Cache
    ie4uinit.exe -show 2>$null

    Write-Success "File associations and icons registered."
} catch {
    Write-Warn "Could not set registry file associations: $_"
}

Write-Success "Installation complete!"
Write-Host "`nRun '$AppId' to launch.`n" -ForegroundColor Green