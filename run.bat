@echo off
chcp 65001 >nul
title نظام مطابقة بيانات السيارات - Vehicle Data Matching System

echo ======================================================================
echo          نظام مطابقة بيانات السيارات الفوري (By Plate Only)
echo ======================================================================
echo.

:: فحص توفر بايثون
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [خطأ] لم يتم العثور على بايثون مثبت في النظام.
    echo يرجى التأكد من تثبيت Python 3.10+ وإضافته إلى متغيرات البيئة PATH.
    pause
    exit /b 1
)

echo [1/3] التحقق من المتطلبات وتجهيز قواعد البيانات...
python -c "import backend.database; backend.database.init_system_db()"

echo [2/3] بدء تشغيل السيرفر المحلي على http://127.0.0.1:8000 ...
echo [3/3] فتح المتصفح تلقائيًا...

start "" http://127.0.0.1:8000

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

pause
