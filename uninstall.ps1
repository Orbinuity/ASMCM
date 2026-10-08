$AppName = "ASMCM"
$InstallDir = "$env:LOCALAPPDATA\Programs\$AppName"
$UninstallerVersion = "1.0.0-windows"

Write-Host "`n=== $AppName Uninstaller v$UninstallerVersion ===" -ForegroundColor Cyan

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
    Write-Host "[✓] $AppName program files removed." -ForegroundColor Green
} else {
    Write-Host "[!] $AppName was not found." -ForegroundColor Yellow
}

# Clean up .asmcx registry associations
$ExtKey = "HKCU:\Software\Classes\.asmcx"
$ProgKey = "HKCU:\Software\Classes\ASMCM.File"

if (Test-Path $ExtKey) { Remove-Item -Recurse -Force $ExtKey -ErrorAction SilentlyContinue }
if (Test-Path $ProgKey) { Remove-Item -Recurse -Force $ProgKey -ErrorAction SilentlyContinue }

Write-Host "[✓] File association cleaned up." -ForegroundColor Green