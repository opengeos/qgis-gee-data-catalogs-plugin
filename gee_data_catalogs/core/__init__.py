"""
GEE Data Catalogs Core Module

This module contains core functionality for the GEE Data Catalogs plugin.
"""

from .ee_utils import (
    initialize_ee,
    try_auto_initialize_ee,
    is_ee_initialized,
    add_ee_layer,
    filter_image_collection,
)
from .catalog_data import (
    get_catalog_data,
    get_categories,
    search_datasets,
    get_dataset_info,
    get_all_datasets,
    fetch_official_catalog,
    fetch_community_catalog,
    refresh_catalogs,
    clear_cache,
)

__all__ = [
    "initialize_ee",
    "try_auto_initialize_ee",
    "is_ee_initialized",
    "add_ee_layer",
    "filter_image_collection",
    "get_catalog_data",
    "get_categories",
    "search_datasets",
    "get_dataset_info",
    "get_all_datasets",
    "fetch_official_catalog",
    "fetch_community_catalog",
    "refresh_catalogs",
    "clear_cache",
]
