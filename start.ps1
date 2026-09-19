# نظام مطابقة بيانات السيارات - تشغيل بنقرة واحدة عبر PowerShell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "         نظام مطابقة بيانات السيارات الفوري (By Plate Only)            " -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan

# التحقق من بايثون
try {
    $pyVer = python --version
    Write-Host "✓ بايثون متوفر: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "❌ خطأ: لم يتم العثور على Python مثبت." -ForegroundColor Red
    exit 1
}

# تهيئة قاعدة البيانات
Write-Host "[1/3] تهيئة قواعد البيانات والمستخدمين الـ 50..." -ForegroundColor Gray
python -c "import backend.database; backend.database.init_system_db()"

# فتح المتصفح
Write-Host "[2/3] فتح المتصفح على http://127.0.0.1:8000 ..." -ForegroundColor Gray
Start-Process "http://127.0.0.1:8000"

# تشغيل السيرفر
Write-Host "[3/3] تشغيل سيرفر الويب المحلي..." -ForegroundColor Green
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
