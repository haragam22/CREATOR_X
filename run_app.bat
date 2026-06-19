@echo off
echo ========================================================
echo Setting up local PUB_CACHE to bypass Windows Path Spaces
echo ========================================================

:: Create a local pub cache directory that doesn't have spaces
set PUB_CACHE=C:\Projects\.pub-cache
if not exist "%PUB_CACHE%" mkdir "%PUB_CACHE%"

:: Navigate into the app directory
cd socialfi_app

:: Run the app
echo Launching the SocialFi App on your Emulator...
flutter run
