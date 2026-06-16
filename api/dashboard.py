from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "web" / "dashboard.html"


@router.get("/dashboard", response_class=HTMLResponse, summary="Operations dashboard")
async def dashboard_page():
    return HTMLResponse(TEMPLATE_PATH.read_text(encoding="utf-8"))
