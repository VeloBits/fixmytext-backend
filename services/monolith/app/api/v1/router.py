"""
API v1 router — aggregates all endpoint sub-routers.

Add new feature routers here as the app grows.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    history,
    passes,
    share,
    subscription,
    text,
    user_data,
)
from app.api.v1.endpoints.auth_register import router as auth_register_router

api_router = APIRouter()

api_router.include_router(text.router)
api_router.include_router(auth.router)
api_router.include_router(auth_register_router, prefix="/auth", tags=["auth"])
api_router.include_router(user_data.router)
api_router.include_router(subscription.router)
api_router.include_router(passes.router)
api_router.include_router(history.router)
api_router.include_router(share.router)
