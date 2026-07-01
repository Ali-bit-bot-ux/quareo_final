"""
Waybills API endpoints.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/waybills", tags=["Waybills"])

@router.post("/merge")
async def merge_waybills(data: dict):
    """Merge waybills into a single PDF."""
    return {"success": True, "pdf_url": "#"}

@router.get("/preview/{waybill_id}")
async def preview_waybill(waybill_id: str):
    """Preview a specific waybill."""
    return {"success": True, "waybill_id": waybill_id}
