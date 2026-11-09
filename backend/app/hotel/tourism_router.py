"""Tourism content endpoints (ADMIN only) — tour packages + local information.

Guest-facing reads live on the guest portal (``/guest-portal/{token}/tourism``)
and return only active rows; these staff endpoints manage the underlying
content rows (content only — no booking/payment integration anywhere).
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.auth.service import write_audit
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.hotel.schemas import (
    LocalInfoCreate,
    LocalInfoPatch,
    LocalInfoResponse,
    TourPackageCreate,
    TourPackagePatch,
    TourPackageResponse,
)
from app.models.tourism import LocalInfo, TourPackage
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["tourism"])


def _serialize_package(row: TourPackage) -> TourPackageResponse:
    return TourPackageResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        duration=row.duration,
        price=row.price,
        image_url=row.image_url,
        contact_number=row.contact_number,
        is_active=row.is_active,
        display_order=row.display_order,
    )


def _serialize_local(row: LocalInfo) -> LocalInfoResponse:
    return LocalInfoResponse(
        id=row.id,
        title=row.title,
        description=row.description,
        location=row.location,
        contact_number=row.contact_number,
        image_url=row.image_url,
        is_active=row.is_active,
        display_order=row.display_order,
    )


@router.get("/tour-packages", response_model=list[TourPackageResponse])
def list_tour_packages(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> list[TourPackageResponse]:
    """List tour packages (ADMIN only)."""
    rows = db.scalars(select(TourPackage).order_by(TourPackage.display_order)).all()
    return [_serialize_package(r) for r in rows]


@router.post("/tour-packages", response_model=TourPackageResponse, status_code=201)
def create_tour_package_route(
    payload: TourPackageCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> TourPackageResponse:
    """Create a tour package (ADMIN only)."""
    verify_csrf(request)
    row = TourPackage(
        name=payload.name,
        description=payload.description,
        duration=payload.duration,
        price=payload.price,
        image_url=str(payload.image_url) if payload.image_url else None,
        contact_number=payload.contact_number,
        display_order=payload.display_order,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="TOUR_PACKAGE_CREATED",
        resource_type="tour_package",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"name": row.name},
    )
    db.commit()
    db.refresh(row)
    return _serialize_package(row)


@router.patch("/tour-packages/{package_id}", response_model=TourPackageResponse)
def patch_tour_package_route(
    package_id: uuid.UUID,
    payload: TourPackagePatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> TourPackageResponse:
    """Update a tour package, including deactivation (ADMIN only)."""
    verify_csrf(request)
    row = db.get(TourPackage, package_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Tour package not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    write_audit(
        db,
        action="TOUR_PACKAGE_UPDATED",
        resource_type="tour_package",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"name": row.name},
    )
    db.commit()
    db.refresh(row)
    return _serialize_package(row)


@router.get("/local-info", response_model=list[LocalInfoResponse])
def list_local_info(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> list[LocalInfoResponse]:
    """List local information entries (ADMIN only)."""
    rows = db.scalars(select(LocalInfo).order_by(LocalInfo.display_order)).all()
    return [_serialize_local(r) for r in rows]


@router.post("/local-info", response_model=LocalInfoResponse, status_code=201)
def create_local_info_route(
    payload: LocalInfoCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> LocalInfoResponse:
    """Create a local information entry (ADMIN only)."""
    verify_csrf(request)
    row = LocalInfo(
        title=payload.title,
        description=payload.description,
        location=payload.location,
        contact_number=payload.contact_number,
        image_url=str(payload.image_url) if payload.image_url else None,
        display_order=payload.display_order,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="LOCAL_INFO_CREATED",
        resource_type="local_info",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"title": row.title},
    )
    db.commit()
    db.refresh(row)
    return _serialize_local(row)


@router.patch("/local-info/{info_id}", response_model=LocalInfoResponse)
def patch_local_info_route(
    info_id: uuid.UUID,
    payload: LocalInfoPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CONTENT_MANAGE)),
) -> LocalInfoResponse:
    """Update a local information entry, including deactivation (ADMIN only)."""
    verify_csrf(request)
    row = db.get(LocalInfo, info_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Local information entry not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    write_audit(
        db,
        action="LOCAL_INFO_UPDATED",
        resource_type="local_info",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"title": row.title},
    )
    db.commit()
    db.refresh(row)
    return _serialize_local(row)
