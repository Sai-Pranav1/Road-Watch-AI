"""
Road Damage Reporting Platform - Main Application Entrypoint
Unified Backend & Frontend Server (FastAPI + YOLOv8 + Supabase + Admin Dashboard)
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from app.config import settings, STATIC_DIR, BASE_DIR
from app.routers import analyze, reports, stats
from app import auth

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="End-to-End Road Damage Detection, Prioritization & Authority Triage Platform",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS setup for hackathon clients and cross-origin tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (JS, CSS, uploaded media assets)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount API routers
app.include_router(analyze.router)
app.include_router(auth.router)
# Reports + stats are authority-only: require the admin session cookie
app.include_router(reports.router, dependencies=[Depends(auth.require_admin)])
app.include_router(stats.router, dependencies=[Depends(auth.require_admin)])

# Template views
templates_dir = BASE_DIR / "app" / "templates"


@app.get("/", response_class=HTMLResponse, tags=["Citizen Web App"])
async def citizen_portal():
    """Renders the Citizen submission interface (Camera upload + GPS auto-pin)."""
    index_file = templates_dir / "citizen.html"
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/admin", response_class=HTMLResponse, tags=["Authority Dashboard"])
async def admin_dashboard(request: Request):
    """Renders the Municipal Authority Admin Triage Dashboard (password protected)."""
    page = "admin.html" if auth.is_admin(request) else "admin_login.html"
    admin_file = templates_dir / page
    return HTMLResponse(content=admin_file.read_text(encoding="utf-8"))


@app.get("/health", tags=["System"])
async def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "supabase_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)
    }


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("🚀 ROAD DAMAGE REPORTING PLATFORM (HACKATHON MVP v2.0)")
    print("="*70)
    print(f" Citizen Web App:       http://localhost:{settings.PORT}/")
    print(f" Admin Triage Map:      http://localhost:{settings.PORT}/admin")
    print(f" Interactive API Docs:  http://localhost:{settings.PORT}/docs")
    print("="*70 + "\n")
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=os.getenv("RELOAD", "false").lower() == "true")
