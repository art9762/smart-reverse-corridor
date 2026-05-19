@echo off
REM Full integration demo: ML pipeline + MQTT + Controller
REM Shows how vehicle detection drives the traffic light controller
REM
REM Prerequisites:
REM   docker compose up -d mosquitto controller influxdb
REM   (or run mosquitto locally on port 1883)

setlocal

set VIDEO=%~1
if "%VIDEO%"=="" set VIDEO=4K Video of Highway Traffic!.mp4

echo ============================================================
echo   Smart Reverse Corridor - Full Integration Demo
echo ============================================================
echo.
echo   ML (YOLOv8) -> MQTT -> Controller -> Traffic Light FSM
echo.
echo ============================================================

REM Check video
if not exist "%VIDEO%" (
    echo ERROR: Video not found: %VIDEO%
    echo Place your highway traffic video in the project root.
    exit /b 1
)

REM Check if MQTT broker is reachable
python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',1883)); s.close()" 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: MQTT broker not reachable on localhost:1883
    echo Start it with: docker compose up -d mosquitto
    echo.
    echo Running without MQTT publishing (visual demo only)...
    echo.
    python scripts/demo_video_pipeline.py --video "%VIDEO%" --skip 2 --loop
) else (
    echo MQTT broker: OK (localhost:1883)
    echo.
    echo Events will be published to: corridor/cam/A/in/event
    echo Controller will react to crossing events in real-time.
    echo.
    python scripts/demo_video_pipeline.py --video "%VIDEO%" --publish --skip 2 --loop --mqtt-host 127.0.0.1
)

endlocal
