"""
مسارات إدارة بيانات السيارات للمستخدم (Dataset Routes)
- رفع واستبدال ملف الـ 2M سجل يوميًا
- فحص إحصائيات البيانات النشطة
- البحث السريع باللوحة
- تفريغ البيانات
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel

from backend.config import UPLOADS_DIR
from backend.auth import get_current_active_user
from backend.database import replace_user_dataset, get_dataset_stats, clear_user_dataset
from backend.matching_engine import quick_search_single_plate

router = APIRouter(prefix="/api/dataset", tags=["إدارة بيانات السيارات"])


class QuickSearchRequest(BaseModel):
    plate: str


@router.get("/stats")
def get_stats(user: dict = Depends(get_current_active_user)):
    """استرجاع إحصائيات قاعدة البيانات النشطة للمستخدم"""
    stats = get_dataset_stats(user["id"])
    return {"success": True, "stats": stats}


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    plate_col: Optional[str] = Form(None),
    chassis_col: Optional[str] = Form(None),
    client_col: Optional[str] = Form(None),
    bank_col: Optional[str] = Form(None),
    user: dict = Depends(get_current_active_user)
):
    """
    رفع واستبدال ملف البيانات الرئيسي للمستخدم (حتى 2,000,000 سجل)
    يدعم CSV و Excel و TSV
    """
    filename = file.filename
    ext = Path(filename).suffix.lower()
    if ext not in ['.csv', '.txt', '.tsv', '.xlsx', '.xls']:
        raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة. الصيغ المدعومة: CSV, Excel (.xlsx), TXT")

    # حفظ الملف مؤقتًا للبدء في المعالجة
    user_upload_dir = UPLOADS_DIR / f"user_{user['id']}"
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = user_upload_dir / f"dataset_upload_{filename}"

    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # استدعاء دالة الاستبدال الذري للبيانات
        result = replace_user_dataset(
            user_id=user["id"],
            file_path=str(temp_file_path),
            plate_col=plate_col if plate_col and plate_col.strip() else None,
            chassis_col=chassis_col if chassis_col and chassis_col.strip() else None,
            client_col=client_col if client_col and client_col.strip() else None,
            bank_col=bank_col if bank_col and bank_col.strip() else None
        )

        return {
            "success": True,
            "message": f"تم استبدال البيانات بنجاح: {result['total_records']:,} سيارة",
            "data": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء معالجة الملف: {str(e)}")

    finally:
        # حذف الملف المؤقت بعد الانتهاء من المعالجة لتوفير المساحة
        if temp_file_path.exists():
            try:
                os.remove(temp_file_path)
            except Exception:
                pass


@router.post("/clear")
def clear_dataset(user: dict = Depends(get_current_active_user)):
    """تفريغ بيانات المستخدم بالكامل"""
    clear_user_dataset(user["id"])
    return {"success": True, "message": "تم تفريغ البيانات بنجاح"}


@router.post("/quick-search")
def quick_search(req: QuickSearchRequest, user: dict = Depends(get_current_active_user)):
    """البحث الفوري عن لوحة واحدة داخل قاعدة بيانات المستخدم"""
    if not req.plate or not req.plate.strip():
        raise HTTPException(status_code=400, detail="يرجى إدخال رقم اللوحة للبحث")

    results = quick_search_single_plate(user["id"], req.plate)
    return {
        "success": True,
        "query": req.plate,
        "total_matches": len(results),
        "results": results
    }
