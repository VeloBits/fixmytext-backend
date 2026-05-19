"""
API v1 router — aggregates all endpoint sub-routers.

Add new feature routers here as the app grows.

NOTE: passes and subscription routes have been extracted to payments-svc.
Kong routes /api/v1/passes and /api/v1/subscription → payments-svc.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    history,
    share,
    user_data,
)
from app.api.v1.endpoints.auth_register import router as auth_register_router

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(auth_register_router, prefix="/auth", tags=["auth"])
api_router.include_router(user_data.router)
api_router.include_router(history.router)
api_router.include_router(share.router)
