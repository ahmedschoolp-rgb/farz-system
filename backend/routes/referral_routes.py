"""
مسارات مطابقة ملفات الإحالة وتصدير التقارير (Referral Matching & Export Routes)
"""

import os
import shutil
import time
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.responses import FileResponse

from backend.config import UPLOADS_DIR
from backend.auth import get_current_active_user
from backend.matching_engine import match_referral_file, get_match_results_page, export_match_results, get_match_map_points

router = APIRouter(prefix="/api/referral", tags=["مطابقة ملفات الإحالة والتصدير"])


@router.post("/match")
async def match_referral(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    plate_col: Optional[str] = Form(None),
    chassis_col: Optional[str] = Form(None),
    client_col: Optional[str] = Form(None),
    bank_col: Optional[str] = Form(None),
    user: dict = Depends(get_current_active_user)
):
    """
    رفع ملف أو عدة ملفات إحالة والبدء في المطابقة الفورية (By Plate Only)
    """
    uploaded_files = []
    if files:
        uploaded_files.extend(files)
    if file and file not in uploaded_files:
        uploaded_files.append(file)

    if not uploaded_files:
        raise HTTPException(status_code=400, detail="يرجى اختيار ملف إحالة واحد على الأقل.")

    user_upload_dir = UPLOADS_DIR / f"user_{user['id']}"
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    temp_paths = []

    try:
        for f in uploaded_files:
            filename = f.filename
            if not filename:
                continue
            ext = Path(filename).suffix.lower()
            if ext not in ['.csv', '.txt', '.tsv', '.xlsx', '.xls']:
                continue
            temp_path = user_upload_dir / f"referral_upload_{int(time.time() * 1000)}_{filename}"
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            temp_paths.append(str(temp_path))

        if not temp_paths:
            raise HTTPException(status_code=400, detail="صيغ ملفات الإحالة غير مدعومة. الصيغ المدعومة: Excel, CSV, TXT")

        # تنفيذ المطابقة لكافة الملفات دفعة واحدة
        result = match_referral_file(
            user_id=user["id"],
            file_path=temp_paths,
            plate_col=plate_col if plate_col and plate_col.strip() else None,
            chassis_col=chassis_col if chassis_col and chassis_col.strip() else None,
            client_col=client_col if client_col and client_col.strip() else None,
            bank_col=bank_col if bank_col and bank_col.strip() else None
        )

        return {
            "success": True,
            "message": f"تمت مطابقة {len(temp_paths)} ملف(ات) بنجاح في {result['execution_time_ms']} ميلي ثانية",
            "summary": result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ أثناء مطابقة ملفات الإحالة: {str(e)}")

    finally:
        for tp in temp_paths:
            p = Path(tp)
            if p.exists():
                try:
                    os.remove(p)
                except Exception:
                    pass


@router.get("/results")
def get_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=500),
    filter_status: str = Query('all', pattern="^(all|matched|unmatched|multiple)$"),
    q: str = Query("", alias="search"),
    user: dict = Depends(get_current_active_user)
):
    """
    استعراض صفحة من نتائج المطابقة الأخيرة مع الفرز والبحث
    """
    results = get_match_results_page(
        user_id=user["id"],
        page=page,
        page_size=page_size,
        filter_status=filter_status,
        search_query=q
    )
    return {"success": True, "data": results}


@router.get("/map-points")
def get_map_points(user: dict = Depends(get_current_active_user)):
    """
    استرجاع مواقع ونقاط كافة السيارات المتطابقة لعرضها على الخريطة التفاعلية
    """
    points = get_match_map_points(user["id"])
    return {"success": True, "count": len(points), "points": points}


@router.get("/export")
def export_results(
    format: str = Query('xlsx', pattern="^(xlsx|csv)$"),
    filter_status: str = Query('all', pattern="^(all|matched|unmatched|multiple)$"),
    user: dict = Depends(get_current_active_user)
):
    """
    تنزيل ملف النتائج بصيغة Excel أو CSV
    """
    try:
        export_file_path = export_match_results(
            user_id=user["id"],
            file_format=format,
            filter_status=filter_status
        )

        filename = os.path.basename(export_file_path)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == 'xlsx' else "text/csv; charset=utf-8"

        return FileResponse(
            path=export_file_path,
            filename=filename,
            media_type=media_type
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
