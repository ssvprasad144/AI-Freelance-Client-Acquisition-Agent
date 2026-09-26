@echo off
setlocal
echo Starting live discovery worker...
echo.
echo The worker discovers public opportunities and auto-qualifies leads.
echo It never sends external messages.
echo.
cd backend
python manage.py run_discovery_cycle --loop
