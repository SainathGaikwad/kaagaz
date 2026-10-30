@echo off
REM One-time push of Kaagaz to github.com/SainathGaikwad/kaagaz
cd /d C:\Users\TTPL-LNV-0319\Downloads\kaagaz
git init
git branch -M main
git config user.name "Sainath Gaikwad"
git config user.email "gaikwadsainath738@gmail.com"
git add .
git commit -m "Kaagaz: register page to a verified Section 479 release list, read by Muse Spark Open"
git remote add origin https://github.com/SainathGaikwad/kaagaz.git
git push -u origin main
echo.
echo If a login window appeared, finish signing in and the upload will complete.
echo When done, the code is at https://github.com/SainathGaikwad/kaagaz
pause
