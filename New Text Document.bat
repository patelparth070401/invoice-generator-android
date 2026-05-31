@echo off
set PYTHONPATH=C:\Users\papa3009\AppData\Roaming\Python\Python312\site-packages;%PYTHONPATH%
"C:\Program Files\Python312\python.exe" -m PyInstaller invoice_app.spec
pause