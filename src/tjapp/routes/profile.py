"""Профиль, онбординг, список залов."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from tj.services import profile as svc
from tjapp.deps import require_user

from ._common import fields_error, get_con

router = APIRouter()


@router.get("/api/profile")
def get_profile(user: dict = Depends(require_user), con=Depends(get_con)):
    p = svc.get_profile(con, user["id"])
    if p is None:
        raise HTTPException(status_code=404, detail="профиль не создан")
    return p


@router.patch("/api/profile")
def patch_profile(body: dict = Body(...), user: dict = Depends(require_user), con=Depends(get_con)):
    """Частичное обновление. Поля: nick, height_cm, weight_kg, sex, age, gym, lang, goal, city, astro."""
    try:
        return svc.update_profile(con, user["id"], body)
    except svc.ProfileError as e:
        return fields_error(e.errors)


@router.get("/api/gyms")
def gyms(user: dict = Depends(require_user), con=Depends(get_con)):
    return svc.list_gyms(con)


@router.get("/api/onboarding")
def onboarding(user: dict = Depends(require_user), con=Depends(get_con)):
    return svc.onboarding_status(con, user["id"])
