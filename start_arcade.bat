@echo off
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
  call .venv\Scripts\activate
  python -m pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
start "Campus Racing Server" cmd /k "python -m uvicorn app:app --host 0.0.0.0 --port 8000"
timeout /t 2 >nul
start "Campus Racing Rig Agent" cmd /k "python rig_agent.py"
start "" pythonw kiosk_browser.py
