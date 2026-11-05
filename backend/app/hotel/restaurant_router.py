"""Restaurant and cab configuration endpoints (ADMIN only).

Public/guest-portal read access is a later phase — these /admin/* routes
require the relevant manage permission and return 401/403 otherwise.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.auth.service import write_audit
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.hotel.schemas import (
    CabInfoCreate,
    CabInfoPatch,
    CabInfoResponse,
    MenuCategoryCreate,
    MenuCategoryPatch,
    MenuCategoryResponse,
    MenuItemCreate,
    MenuItemPatch,
    MenuItemResponse,
    RestaurantPatch,
    RestaurantResponse,
)
from app.models.cab_info import CabInfo
from app.models.restaurant import MenuCategory, MenuItem, RestaurantInfo
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin-restaurant"])


def _get_or_create_restaurant(db: DBSession) -> RestaurantInfo:
    row = db.scalar(select(RestaurantInfo).where(RestaurantInfo.singleton_key == 1))
    if row is None:
        row = RestaurantInfo(name="Restaurant")
        db.add(row)
        db.flush()
    return row


def _serialize_restaurant(row: RestaurantInfo) -> RestaurantResponse:
    return RestaurantResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        contact_number=row.contact_number,
        opening_hours=row.opening_hours,
        is_active=row.is_active,
    )


def _serialize_category(row: MenuCategory) -> MenuCategoryResponse:
    return MenuCategoryResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        display_order=row.display_order,
        is_active=row.is_active,
    )


def _serialize_item(row: MenuItem) -> MenuItemResponse:
    return MenuItemResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        price=row.price,
        image_url=row.image_url,
        category_id=row.category_id,
        is_vegetarian=row.is_vegetarian,
        is_available=row.is_available,
        display_order=row.display_order,
    )


def _serialize_cab(row: CabInfo) -> CabInfoResponse:
    return CabInfoResponse(
        id=row.id,
        company_name=row.company_name,
        description=row.description,
        contact_number=row.contact_number,
        website_url=row.website_url,
        service_description=row.service_description,
        is_active=row.is_active,
        display_order=row.display_order,
    )


# --- Restaurant ---------------------------------------------------------


@router.get("/restaurant", response_model=RestaurantResponse | None)
def get_restaurant(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> RestaurantResponse | None:
    """Return restaurant info (null until configured)."""
    row = db.scalar(select(RestaurantInfo).where(RestaurantInfo.singleton_key == 1))
    return _serialize_restaurant(row) if row is not None else None


@router.patch("/restaurant", response_model=RestaurantResponse)
def patch_restaurant(
    payload: RestaurantPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> RestaurantResponse:
    """Create-or-update restaurant info (ADMIN only)."""
    verify_csrf(request)
    row = _get_or_create_restaurant(db)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    row.updated_by = actor.id
    write_audit(
        db,
        action="RESTAURANT_INFO_UPDATED",
        resource_type="restaurant_info",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _serialize_restaurant(row)


@router.get("/menu-categories", response_model=list[MenuCategoryResponse])
def list_menu_categories(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> list[MenuCategoryResponse]:
    """List menu categories."""
    rows = db.scalars(select(MenuCategory).order_by(MenuCategory.display_order)).all()
    return [_serialize_category(r) for r in rows]


@router.post("/menu-categories", response_model=MenuCategoryResponse, status_code=201)
def create_menu_category_route(
    payload: MenuCategoryCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> MenuCategoryResponse:
    """Create a menu category (ADMIN only)."""
    verify_csrf(request)
    if db.scalar(select(MenuCategory).where(MenuCategory.name == payload.name)):
        raise ApiError(409, "CONFLICT", "Menu category name already exists.")
    row = MenuCategory(
        name=payload.name, description=payload.description, display_order=payload.display_order
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="MENU_CATEGORY_CREATED",
        resource_type="menu_category",
        resource_id=str(row.id),
        actor_user_id=actor.id,
    )
    db.commit()
    db.refresh(row)
    return _serialize_category(row)


@router.patch("/menu-categories/{category_id}", response_model=MenuCategoryResponse)
def patch_menu_category_route(
    category_id: uuid.UUID,
    payload: MenuCategoryPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> MenuCategoryResponse:
    """Update a menu category, including deactivation (ADMIN only)."""
    verify_csrf(request)
    row = db.get(MenuCategory, category_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Menu category not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    write_audit(
        db,
        action="MENU_CATEGORY_UPDATED",
        resource_type="menu_category",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _serialize_category(row)


@router.get("/menu-items", response_model=list[MenuItemResponse])
def list_menu_items(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
    category_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[MenuItemResponse]:
    """List menu items, optionally filtered by category, with pagination."""
    stmt = select(MenuItem)
    if category_id is not None:
        stmt = stmt.where(MenuItem.category_id == category_id)
    rows = db.scalars(
        stmt.order_by(MenuItem.display_order).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [_serialize_item(r) for r in rows]


@router.post("/menu-items", response_model=MenuItemResponse, status_code=201)
def create_menu_item_route(
    payload: MenuItemCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> MenuItemResponse:
    """Create a menu item (ADMIN only)."""
    verify_csrf(request)
    if db.get(MenuCategory, payload.category_id) is None:
        raise ApiError(404, "NOT_FOUND", "Menu category not found.")
    row = MenuItem(
        name=payload.name,
        description=payload.description,
        price=payload.price,
        image_url=str(payload.image_url) if payload.image_url else None,
        category_id=payload.category_id,
        is_vegetarian=payload.is_vegetarian,
        display_order=payload.display_order,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="MENU_ITEM_CREATED",
        resource_type="menu_item",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"name": row.name, "price": str(row.price)},
    )
    db.commit()
    db.refresh(row)
    return _serialize_item(row)


@router.patch("/menu-items/{item_id}", response_model=MenuItemResponse)
def patch_menu_item_route(
    item_id: uuid.UUID,
    payload: MenuItemPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> MenuItemResponse:
    """Update a menu item, including price and availability (ADMIN only)."""
    verify_csrf(request)
    row = db.get(MenuItem, item_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Menu item not found.")
    if payload.category_id is not None and db.get(MenuCategory, payload.category_id) is None:
        raise ApiError(404, "NOT_FOUND", "Menu category not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    write_audit(
        db,
        action="MENU_ITEM_UPDATED",
        resource_type="menu_item",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _serialize_item(row)


# --- Cab providers ------------------------------------------------------


@router.get("/cab-providers", response_model=list[CabInfoResponse])
def list_cab_providers(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> list[CabInfoResponse]:
    """List cab providers."""
    rows = db.scalars(select(CabInfo).order_by(CabInfo.display_order)).all()
    return [_serialize_cab(r) for r in rows]


@router.post("/cab-providers", response_model=CabInfoResponse, status_code=201)
def create_cab_provider_route(
    payload: CabInfoCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> CabInfoResponse:
    """Create a cab provider (ADMIN only). URL + phone validated."""
    verify_csrf(request)
    row = CabInfo(
        company_name=payload.company_name,
        description=payload.description,
        contact_number=payload.contact_number,
        website_url=str(payload.website_url) if payload.website_url else None,
        service_description=payload.service_description,
        display_order=payload.display_order,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="CAB_PROVIDER_CREATED",
        resource_type="cab_info",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"company_name": row.company_name},
    )
    db.commit()
    db.refresh(row)
    return _serialize_cab(row)


@router.patch("/cab-providers/{provider_id}", response_model=CabInfoResponse)
def patch_cab_provider_route(
    provider_id: uuid.UUID,
    payload: CabInfoPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> CabInfoResponse:
    """Update a cab provider, including deactivation (ADMIN only)."""
    verify_csrf(request)
    row = db.get(CabInfo, provider_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Cab provider not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    write_audit(
        db,
        action="CAB_PROVIDER_UPDATED",
        resource_type="cab_info",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _serialize_cab(row)
