"""
مسارات المصادقة والمستخدمين (Auth Routes)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from backend.auth import (
    authenticate_user, create_session, destroy_session, 
    get_current_active_user, get_all_users_list, security_bearer
)

router = APIRouter(prefix="/api/auth", tags=["المصادقة والمستخدمين"])


class LoginRequest(BaseModel):
    username: str
    password: str


class SwitchUserRequest(BaseModel):
    user_id: int


@router.post("/login")
def login(req: LoginRequest):
    """تسجيل الدخول بالاسم وكلمة المرور"""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")

    token = create_session(user["id"])
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"]
        }
    }


@router.get("/me")
def get_me(user: dict = Depends(get_current_active_user)):
    """جلب بيانات المستخدم الحالي النشط"""
    return {"success": True, "user": user}


@router.post("/logout")
def logout(credentials=Depends(security_bearer)):
    """تسجيل الخروج وإنهاء الجلسة"""
    if credentials:
        destroy_session(credentials.credentials)
    return {"success": True, "message": "تم تسجيل الخروج بنجاح"}


@router.get("/users")
def get_users():
    """عرض قائمة المستخدمين لتسهيل التبديل والاستخدام السلس"""
    users = get_all_users_list()
    return {"success": True, "users": users}


@router.post("/quick-switch")
def quick_switch(req: SwitchUserRequest):
    """تبديل سريع للمستخدم (مفيد لتجربة الـ 50 مستخدمًا دون الحاجة لإعادة كتابة كلمات المرور)"""
    users = get_all_users_list()
    target_user = next((u for u in users if u["id"] == req.user_id), None)
    if not target_user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    token = create_session(target_user["id"])
    return {
        "success": True,
        "token": token,
        "user": target_user
    }
