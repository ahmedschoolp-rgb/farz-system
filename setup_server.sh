#!/bin/bash
# ==============================================================================
# سكربت التثبيت والتشغيل التلقائي لنظام مطابقة بيانات السيارات على السيرفر السحابي
# One-Click Setup Script for Production Linux VPS (Ubuntu / Debian)
# ==============================================================================

set -e

echo "========================================================="
echo "🚀 جاري إعداد وتجهيز نظام مطابقة بيانات السيارات للإنتاج..."
echo "========================================================="

# 1. تحديث حزم النظام
echo "📦 1. تحديث حزم السيرفر..."
sudo apt-get update -y && sudo apt-get upgrade -y

# 2. تثبيت Docker و Docker Compose إن لم يكونا مثبتين
if ! command -v docker &> /dev/null; then
    echo "🐳 2. تثبيت Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    sudo usermod -aG docker $USER
fi

# 3. التأكد من تثبيت docker compose
echo "🔧 3. التحقق من Docker Compose..."
sudo apt-get install -y docker-compose-plugin

# 4. تجهيز مجلدات البيانات
echo "📂 4. تجهيز مجلدات البيانات والصلاحيات..."
mkdir -p data/users data/exports data/uploads data/samples
chmod -R 777 data

# 5. بناء وتشغيل الحاوية في الخلفية
echo "🏗️ 5. بناء الحاوية وتشغيل النظام..."
docker compose down || true
docker compose build
docker compose up -d

echo "========================================================="
echo "✅ تم تشغيل النظام بنجاح 100%!"
echo "🌐 يمكنك الآن فتح الموقع في المتصفح عبر عنوان IP السيرفر مباشرة:"
echo "👉 http://$(curl -s ifconfig.me)"
echo "========================================================="
