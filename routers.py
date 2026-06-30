from fastapi import APIRouter
from controller import (
    profile_controller,
    seller_controller,
    category_controller,
    look_controller,
    feed_controller,
    swipe_controller,
    wardrobe_controller,
)

router = APIRouter()

router.include_router(profile_controller.router)
router.include_router(seller_controller.router)
router.include_router(category_controller.router)
router.include_router(look_controller.router)
router.include_router(feed_controller.router)
router.include_router(swipe_controller.router)
router.include_router(wardrobe_controller.router)
