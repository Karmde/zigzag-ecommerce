from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.templates import templates
from database.database import get_db
from services import product_services

router = APIRouter()

@router.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    favorite_products = product_services.get_random_products(db, limit=4)
    latest_products = product_services.get_latest_products(db, limit=4)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "favorite_products": favorite_products,
            "latest_products": latest_products,
        },
    )
