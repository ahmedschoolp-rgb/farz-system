"""
سيرفر التطبيق الرئيسي (Main FastAPI Application Server)
نظام مطابقة بيانات السيارات (Vehicle Data Matching System)
"""

import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# ضبط ترميز الإخراج للطرفية لدعم اللغة العربية في ويندوز
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from backend.database import init_system_db
from backend.routes.auth_routes import router as auth_router
from backend.routes.dataset_routes import router as dataset_router
from backend.routes.referral_routes import router as referral_router

# إنشاء تطبيق FastAPI
app = FastAPI(
    title="Vehicle Data Matching System",
    description="نظام ويب فائق السرعة لمطابقة بيانات السيارات وملفات الإحالة (By Plate Only)",
    version="2.0.0"
)

# إعداد CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# تضمين مسارات الـ API
app.include_router(auth_router)
app.include_router(dataset_router)
app.include_router(referral_router)


@app.on_event("startup")
def startup_event():
    """تهيئة قواعد البيانات عند بدء تشغيل السيرفر"""
    init_system_db()
    print("================================================================")
    print("  نظام مطابقة بيانات السيارات الفوري (Vehicle Data Matching System)")
    print("  السيرفر يعمل الآن بنجاح على: http://127.0.0.1:8000")
    print("================================================================")


@app.get("/api/health")
def health_check():
    """فحص صحة السيرفر"""
    return {
        "status": "healthy",
        "system": "Vehicle Data Matching System",
        "engine": "DuckDB + SQLite"
    }


# مسار ملفات الواجهة الأمامية
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

    @app.get("/")
    def serve_frontend_root():
        index_file = FRONTEND_DIR / "index.html"
        return FileResponse(str(index_file))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
