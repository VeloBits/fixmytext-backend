"""
API v1 router - aggregates passes and subscription sub-routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import passes, subscription

api_router = APIRouter()

api_router.include_router(passes.router)
api_router.include_router(subscription.router)
