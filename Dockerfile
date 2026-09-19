# Dockerfile for Vehicle Data Matching System (Production)
FROM python:3.12-slim

# ضبط متغيرات البيئة للبايثون
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# تثبيت متطلبات النظام الأساسية
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# تثبيت الاعتماديات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملفات المشروع
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# إنشاء مجلدات البيانات
RUN mkdir -p data/users data/exports data/uploads data/samples

# المنفذ الافتراضي
EXPOSE 8000

# تشغيل الخادم مع 4 عمال (workers) لتحمل ضغط الـ 50 مستخدم بالتوازي
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
