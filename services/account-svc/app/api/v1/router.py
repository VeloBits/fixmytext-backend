"""
API v1 router — aggregates auth, user_data, history, and share sub-routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, auth_register, history, share, user_data

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(auth_register.router, prefix="/auth", tags=["Auth"])
api_router.include_router(user_data.router)
api_router.include_router(history.router)
api_router.include_router(share.router)
