from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import logging

from app.core.config import settings
from app.api.routes import router as api_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Wcoflix Anime Downloader - Generate batch download links for IDM, AB Downloader, and more",
    version="1.0.0",
    debug=settings.debug
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

# Serve frontend static files (built React app)
frontend_build = "/app/frontend/build"
if os.path.exists(frontend_build):
    app.mount("/static", StaticFiles(directory=f"{frontend_build}/static"), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Serve index.html for all non-API routes (SPA routing)
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        index_path = os.path.join(frontend_build, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend not built"}

@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "api": "/api"
    }