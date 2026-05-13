@echo off
cd /d %~dp0\..
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist data mkdir data
set PYTHONPATH=.
python scripts\seed_workspace.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
