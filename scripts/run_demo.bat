@echo off
REM Smart Reverse Corridor — quick ML demo launcher
REM Usage: scripts\run_demo.bat [video_file]

setlocal

set VIDEO=%~1
if "%VIDEO%"=="" set VIDEO=4K Video of Highway Traffic!.mp4

echo ============================================
echo   Smart Reverse Corridor - ML Demo
echo ============================================
echo.

REM Check if video exists
if not exist "%VIDEO%" (
    echo ERROR: Video file not found: %VIDEO%
    echo.
    echo Place your video file in the project root or provide the path:
    echo   scripts\run_demo.bat "path\to\video.mp4"
    exit /b 1
)

REM Check Python deps
python -c "import ultralytics" 2>nul
if errorlevel 1 (
    echo Installing ML dependencies...
    pip install -r services\ml\requirements.txt
    pip install opencv-python
)

echo Starting ML pipeline on: %VIDEO%
echo.

python scripts/demo_video_pipeline.py --video "%VIDEO%" --skip 2 --loop

endlocal
