@echo off
rem Builds dist\Gota\Gota.exe (about 12 minutes).  build.bat        -> models are linked next to the exe (no copy)
rem                                                 build.bat copy   -> models are copied (portable folder, ~5 GB more)
cd /d "%~dp0"
rem remove only the LINK to models before PyInstaller cleans dist (rmdir on a junction never touches the target)
if exist "dist\Gota\models" rmdir "dist\Gota\models" 2>nul
".venv\Scripts\python.exe" -m PyInstaller Gota.spec --noconfirm --clean --distpath dist --workpath build
if errorlevel 1 exit /b 1
if /i "%1"=="copy" (
  robocopy "models" "dist\Gota\models" /E /NFL /NDL /NJH /NJS /NP
) else (
  mklink /J "dist\Gota\models" "%~dp0models"
)
echo Pronto: dist\Gota\Gota.exe
