"""Composable HTTP API modules for the DataForge modular monolith."""

from .assets import build_assets_router
from .applications import build_applications_router
from .dashboard import build_dashboard_router
from .delivery import build_delivery_router
from .documents import build_documents_router
from .indexing import build_indexing_router
from .processing import build_processing_router

__all__ = [
    "build_assets_router",
    "build_applications_router",
    "build_dashboard_router",
    "build_delivery_router",
    "build_documents_router",
    "build_indexing_router",
    "build_processing_router",
]
