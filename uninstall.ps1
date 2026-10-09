$AppName = "ASMCM"
$InstallDir = "$env:LOCALAPPDATA\Programs\$AppName"
$UninstallerVersion = "1.2.0-windows"

Write-Host "`n=== $AppName Uninstaller v$UninstallerVersion ===" -ForegroundColor Cyan

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
    Write-Host "[✓] $AppName program files removed." -ForegroundColor Green
} else {
    Write-Host "[!] $AppName was not found." -ForegroundColor Yellow
}

# Clean up Start Menu Shortcut
$StartMenuShortcut = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\$AppName.lnk"
if (Test-Path $StartMenuShortcut) {
    Remove-Item -Force $StartMenuShortcut -ErrorAction SilentlyContinue
}

# Clean up registry entries
$Keys = @(
    "HKCU:\Software\Classes\.asmc",
    "HKCU:\Software\Classes\.asmcx",
    "HKCU:\Software\Classes\ASMCM.AsmcFile",
    "HKCU:\Software\Classes\ASMCM.AsmcxFile"
)

foreach ($Key in $Keys) {
    if (Test-Path $Key) {
        Remove-Item -Recurse -Force $Key -ErrorAction SilentlyContinue
    }
}

# Refresh Icon Cache
ie4uinit.exe -show 2>$null

Write-Host "[✓] File associations, Start Menu shortcuts, and registry cleaned up." -ForegroundColor Green