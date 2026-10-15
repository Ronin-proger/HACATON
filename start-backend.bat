@echo off
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r backend\requirements.txt
python scripts\generate_samples.py
python scripts\generate_docs.py
set PYTHONPATH=%cd%\backend
set DETECTOR_BACKEND=demo
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
