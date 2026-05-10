from fastapi import APIRouter
from controller import usuario_controller
from controller import company_controller

router = APIRouter()


router.include_router(usuario_controller.router)
router.include_router(company_controller.router)