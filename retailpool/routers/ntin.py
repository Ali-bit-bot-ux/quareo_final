"""
NTIN Router — API endpoints for NTIN marking and НКТ integration.

Endpoints:
  - Product CRUD with NTIN status tracking
  - AI auto-fill (ТН ВЭД code + Kazakh translation)
  - Submit to НКТ
  - ТН ВЭД code search
  - User seller settings (API keys)
  - Stats dashboard
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from retailpool.database import async_session_factory
from retailpool.services.ntin_service import NtinService
from retailpool.models.ntin import NtinStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ntin", tags=["NTIN Marking"])


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════

class NtinProductCreate(BaseModel):
    title_ru: str = Field(..., min_length=2, max_length=512)
    description_ru: str | None = None
    barcode: str | None = None
    kaspi_sku: str | None = None
    brand: str | None = None
    country_of_origin: str | None = "Китай"
    unit_of_measure: str | None = "шт"
    weight_kg: float | None = None
    price: float | None = None
    image_url: str | None = None


class NtinProductResponse(BaseModel):
    id: str
    title_ru: str
    title_kz: str | None = None
    description_ru: str | None = None
    description_kz: str | None = None
    barcode: str | None = None
    kaspi_sku: str | None = None
    ntin_code: str | None = None
    nkt_request_id: int | None = None
    oktru_code: str | None = None
    tn_ved_code: str | None = None
    tn_ved_name: str | None = None
    brand: str | None = None
    country_of_origin: str | None = None
    unit_of_measure: str | None = None
    weight_kg: float | None = None
    price: float | None = None
    image_url: str | None = None
    status: str
    revision_comment: str | None = None
    created_at: str
    updated_at: str
    submitted_at: str | None = None
    approved_at: str | None = None


class NtinProductUpdate(BaseModel):
    title_ru: str | None = None
    title_kz: str | None = None
    description_ru: str | None = None
    description_kz: str | None = None
    barcode: str | None = None
    tn_ved_code: str | None = None
    tn_ved_name: str | None = None
    oktru_code: str | None = None
    brand: str | None = None
    country_of_origin: str | None = None
    unit_of_measure: str | None = None
    weight_kg: float | None = None
    price: float | None = None


class TnVedSearchRequest(BaseModel):
    query: str = Field(..., min_length=2)


class TnVedResult(BaseModel):
    code: str
    name: str


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)


class SellerSettingsRequest(BaseModel):
    kaspi_api_key: str | None = None
    kaspi_merchant_id: str | None = None
    kaspi_shop_name: str | None = None
    nkt_api_key: str | None = None


class SellerSettingsResponse(BaseModel):
    has_kaspi_key: bool = False
    kaspi_merchant_id: str | None = None
    kaspi_shop_name: str | None = None
    has_nkt_key: bool = False


class BulkImportRequest(BaseModel):
    products: list[NtinProductCreate]


class NtinStatsResponse(BaseModel):
    total: int = 0
    draft: int = 0
    ai_filled: int = 0
    ready: int = 0
    submitted: int = 0
    revision: int = 0
    approved: int = 0
    rejected: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Helper: get mock user_id (will use real auth later)
# ═══════════════════════════════════════════════════════════════════════════

# Use a deterministic UUID for demo/MVP until auth is properly wired
DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _product_to_response(p) -> NtinProductResponse:
    return NtinProductResponse(
        id=str(p.id),
        title_ru=p.title_ru,
        title_kz=p.title_kz,
        description_ru=p.description_ru,
        description_kz=p.description_kz,
        barcode=p.barcode,
        kaspi_sku=p.kaspi_sku,
        ntin_code=p.ntin_code,
        nkt_request_id=p.nkt_request_id,
        oktru_code=p.oktru_code,
        tn_ved_code=p.tn_ved_code,
        tn_ved_name=p.tn_ved_name,
        brand=p.brand,
        country_of_origin=p.country_of_origin,
        unit_of_measure=p.unit_of_measure,
        weight_kg=p.weight_kg,
        price=p.price,
        image_url=p.image_url,
        status=p.status,
        revision_comment=p.revision_comment,
        created_at=p.created_at.isoformat() if p.created_at else "",
        updated_at=p.updated_at.isoformat() if p.updated_at else "",
        submitted_at=p.submitted_at.isoformat() if p.submitted_at else None,
        approved_at=p.approved_at.isoformat() if p.approved_at else None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/products", response_model=list[NtinProductResponse])
async def list_products(status: str | None = None):
    """List all NTIN products for the current user."""
    async with async_session_factory() as session:
        svc = NtinService(session)
        products = await svc.get_products(DEMO_USER_ID, status_filter=status)
        return [_product_to_response(p) for p in products]


@router.get("/products/{product_id}", response_model=NtinProductResponse)
async def get_product(product_id: str):
    """Get a single NTIN product."""
    async with async_session_factory() as session:
        svc = NtinService(session)
        product = await svc.get_product(uuid.UUID(product_id), DEMO_USER_ID)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return _product_to_response(product)


@router.post("/products", response_model=NtinProductResponse)
async def create_product(data: NtinProductCreate):
    """Create a new NTIN product card."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            product = await svc.create_product(DEMO_USER_ID, data.model_dump())
            return _product_to_response(product)


@router.put("/products/{product_id}", response_model=NtinProductResponse)
async def update_product(product_id: str, data: NtinProductUpdate):
    """Update an NTIN product card."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            product = await svc.get_product(uuid.UUID(product_id), DEMO_USER_ID)
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")

            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(product, key, value)

            # If user manually edits after AI fill, mark as ready
            if product.status == NtinStatus.AI_FILLED:
                product.status = NtinStatus.READY

            return _product_to_response(product)


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    """Delete an NTIN product card."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            product = await svc.get_product(uuid.UUID(product_id), DEMO_USER_ID)
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            await session.delete(product)
            return {"status": "deleted", "id": product_id}


@router.post("/products/{product_id}/ai-fill", response_model=NtinProductResponse)
async def ai_fill_product(product_id: str):
    """AI auto-fill: ТН ВЭД code + Kazakh translation."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            product = await svc.ai_fill_product(uuid.UUID(product_id), DEMO_USER_ID)
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            return _product_to_response(product)


@router.post("/products/{product_id}/submit", response_model=NtinProductResponse)
async def submit_product(product_id: str):
    """Submit product card to НКТ for NTIN assignment."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            product = await svc.submit_to_nkt(uuid.UUID(product_id), DEMO_USER_ID)
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            return _product_to_response(product)


@router.post("/products/{product_id}/check-status", response_model=NtinProductResponse)
async def check_product_status(product_id: str):
    """Check the status of a submitted product in НКТ."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            product = await svc.check_nkt_status(uuid.UUID(product_id), DEMO_USER_ID)
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            return _product_to_response(product)


@router.post("/sync")
async def sync_nkt_requests():
    """Sync statuses of all submitted products from НКТ."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            result = await svc.sync_nkt_requests(DEMO_USER_ID)
            return result


@router.post("/bulk-import", response_model=list[NtinProductResponse])
async def bulk_import(data: BulkImportRequest):
    """Bulk import products for NTIN processing."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            products = await svc.bulk_import(
                DEMO_USER_ID,
                [p.model_dump() for p in data.products]
            )
            return [_product_to_response(p) for p in products]


@router.get("/stats", response_model=NtinStatsResponse)
async def get_stats():
    """Get NTIN status counts for the current user."""
    async with async_session_factory() as session:
        svc = NtinService(session)
        stats = await svc.get_stats(DEMO_USER_ID)
        return NtinStatsResponse(**stats)


# ── ТН ВЭД Search ───────────────────────────────────────────────────────

@router.post("/tn-ved/search", response_model=list[TnVedResult])
async def search_tn_ved(data: TnVedSearchRequest):
    """Search ТН ВЭД ЕАЭС codes by product description."""
    results = NtinService.search_tn_ved(data.query)
    return [TnVedResult(**r) for r in results]


# ── Translation ─────────────────────────────────────────────────────────

@router.post("/translate")
async def translate_text(data: TranslateRequest):
    """Translate Russian text to Kazakh."""
    kz = NtinService.translate_to_kazakh(data.text)
    return {"original": data.text, "translated": kz}


# ── Seller Settings ──────────────────────────────────────────────────────

@router.get("/settings", response_model=SellerSettingsResponse)
async def get_settings():
    """Get current user's seller settings (keys masked)."""
    async with async_session_factory() as session:
        svc = NtinService(session)
        settings = await svc.get_settings(DEMO_USER_ID)
        if not settings:
            return SellerSettingsResponse()
        return SellerSettingsResponse(
            has_kaspi_key=bool(settings.kaspi_api_key),
            kaspi_merchant_id=settings.kaspi_merchant_id,
            kaspi_shop_name=settings.kaspi_shop_name,
            has_nkt_key=bool(settings.nkt_api_key),
        )


@router.post("/settings", response_model=SellerSettingsResponse)
async def save_settings(data: SellerSettingsRequest):
    """Save seller API keys and settings."""
    async with async_session_factory() as session:
        async with session.begin():
            svc = NtinService(session)
            settings = await svc.save_settings(DEMO_USER_ID, data.model_dump(exclude_unset=True))
            return SellerSettingsResponse(
                has_kaspi_key=bool(settings.kaspi_api_key),
                kaspi_merchant_id=settings.kaspi_merchant_id,
                kaspi_shop_name=settings.kaspi_shop_name,
                has_nkt_key=bool(settings.nkt_api_key),
            )
