@echo off
echo ========================================================
echo ResumeXpert Server Starter
echo ========================================================
echo.
echo Applying database updates...
python manage.py makemigrations
python manage.py migrate
echo.
echo Starting the server...
python manage.py runserver
pause
