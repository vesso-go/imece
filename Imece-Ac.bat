@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Imece
rem 1) Klasordeki hazir Python (kurulum gerektirmez). pythonw ile acilir: siyah pencere kalmaz,
rem    bu pencere hemen kapanir. Imece'yi kapatmak icin uygulamadaki "Imece'yi kapat" dugmesi kullanilir.
if exist "python\pythonw.exe" (
  "python\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    start "" "python\pythonw.exe" imece.py %*
    exit /b 0
  )
)
rem 2) Bilgisayarda kurulu Python. (Windows'un "python" kisayolu Python kurulu degilken magazayi acar; o yuzden once deneniyor.)
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
  py -3 imece.py %*
  goto son
)
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
  python imece.py %*
  goto son
)
echo.
echo   ============================================================
echo    IMECE ACILAMADI
echo   ============================================================
echo.
if exist "python\pythonw.exe" (
  echo    Klasordeki hazir Python bu bilgisayarda calismadi.
  echo    Imece, 64 bit Windows 10 ya da Windows 11 ister.
) else (
  echo    Bu pakette hazir Python yok ve bilgisayarda da Python kurulu degil.
  echo    En kolayi: Imece'nin "windows" paketini indir; onda her sey hazirdir.
)
echo.
echo    Yine de bu klasoru kullanmak istersen (bir kere, internet varken):
echo      1. https://www.python.org/downloads/ adresinden Python'u indir.
echo      2. Kurulumun ilk ekraninda "Add python.exe to PATH" kutusunu isaretle.
echo      3. Kurulum bitince bu dosyaya yeniden cift tikla.
echo.
pause
exit /b 1
:son
if errorlevel 1 pause
