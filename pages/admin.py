from fastapi import APIRouter, Request, Depends
from core.templates import templates
from dependencies.auth_dependency import get_current_admin_from_cookie

from api import admin_api

router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_admin_from_cookie)])

router.include_router(admin_api.router)

@router.get("/admin-dashboard")
async def admin_dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/admin_dashboard.html"
    )

@router.get("/add-product")
async def add_product(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/add_product.html"
    )
