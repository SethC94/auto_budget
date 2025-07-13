@echo off
:MENU
cls
echo ===============================
echo   Git Helper for Budget App
echo ===============================
echo.
echo 1. Pull latest on current branch
echo 2. Change branch
echo 3. Check git status
echo 4. List all branches
echo 5. Stash local changes
echo 6. Apply last stash
echo 7. Add and commit all changes
echo 8. Push current branch
echo 9. Exit
echo.
set /p choice="Select an option (1-9): "

if "%choice%"=="1" goto PULL
if "%choice%"=="2" goto CHANGE_BRANCH
if "%choice%"=="3" goto STATUS
if "%choice%"=="4" goto BRANCHES
if "%choice%"=="5" goto STASH
if "%choice%"=="6" goto APPLY_STASH
if "%choice%"=="7" goto ADD_COMMIT
if "%choice%"=="8" goto PUSH
if "%choice%"=="9" exit

goto MENU

:PULL
git pull
pause
goto MENU

:CHANGE_BRANCH
git branch
set /p branch="Enter branch to switch to: "
git checkout %branch%
pause
goto MENU

:STATUS
git status
pause
goto MENU

:BRANCHES
git branch -a
pause
goto MENU

:STASH
git stash
pause
goto MENU

:APPLY_STASH
git stash apply
pause
goto MENU

:ADD_COMMIT
set /p msg="Enter commit message: "
git add .
git commit -m "%msg%"
pause
goto MENU

:PUSH
git push
pause
goto MENU
