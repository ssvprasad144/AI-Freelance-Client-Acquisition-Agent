@echo off
setlocal
echo Starting follow-up worker...
echo.
echo The worker only marks approved follow-ups as DUE.
echo It never sends external messages.
echo.
cd backend
python manage.py process_due_followups --loop
