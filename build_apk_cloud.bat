@echo off
echo ==========================================================
echo    Automated Android APK Cloud Builder
echo ==========================================================
echo.
echo We will now log you into GitHub securely to build the APK.
echo Please follow the prompts to log in (select GitHub.com, HTTPS, and Login with a web browser).
echo.
pause

REM Add gh to path
set PATH=%cd%\bin;%PATH%

REM Login to GitHub
gh auth login

echo.
echo Initializing Git Repository...
git init
git add .
git commit -m "Automated Flet App Commit for APK Build"
git branch -M main

echo.
echo Creating GitHub Repository and Pushing...
gh repo create invoice-app-android --public --source=. --push

echo.
echo ==========================================================
echo SUCCESS! Your app is now building in the cloud!
echo Go to: https://github.com/
echo Find the "invoice-app-android" repository and click the "Actions" tab.
echo In about 5 minutes, your APK will be ready to download!
echo ==========================================================
pause
