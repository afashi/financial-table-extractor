from fastapi import APIRouter

from apps.core_service.app.api.routes.tasks import router as task_router

api_router = APIRouter()
api_router.include_router(task_router)
