# ============================================================
# Run this in PowerShell to install tray dependencies
# ============================================================
Write-Host "Installing tray app dependencies..." -ForegroundColor Cyan
pip install pystray Pillow pywin32 keyboard -q
Write-Host "All done!" -ForegroundColor Green
Write-Host ""
Write-Host "Now run: python tray_app.py" -ForegroundColor Yellow
