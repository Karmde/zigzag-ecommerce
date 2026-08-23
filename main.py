from dotenv import load_dotenv
from core.templates import templates

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.auth_api import router as auth_router
from api.product_api import router as product_router
from api.search_api import router as search_router
from api.catalog_api import router as catalog_router
from api.cart_api import router as cart_router
from api.wishlist_api import router as wishlist_router
from api.coupon_api import router as coupon_router
from api.address_api import router as address_router

from pages.auth import router as auth_pages_router
from pages.home import router as home_pages_router
from pages.admin import router as admin_pages_router
from pages.product import router as product_pages_router
from pages.user import router as user_pages_router

app = FastAPI()

# Static files
app.mount("/images", StaticFiles(directory="images"), name="images")
app.mount("/js", StaticFiles(directory="js"), name="js")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "https://inmost-blowzily-jackqueline.ngrok-free.dev",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Page Routes
app.include_router(home_pages_router)
app.include_router(auth_pages_router)
app.include_router(admin_pages_router)
app.include_router(product_pages_router)
app.include_router(user_pages_router)

@app.get("/task")
async def verify_email(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="task/task.html"
    )

# Api router
app.include_router(auth_router)
app.include_router(product_router)
app.include_router(search_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(wishlist_router)
app.include_router(coupon_router)
app.include_router(address_router)