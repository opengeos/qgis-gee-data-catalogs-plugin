"""Persistent user state for the GEE Data Catalogs plugin."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from qgis.PyQt.QtCore import QSettings

SETTINGS_PREFIX = "GeeDataCatalogs/"
MAX_RECENTS = 30
MAX_EXPORT_HISTORY = 50


DEFAULT_RECIPES: List[Dict[str, Any]] = [
    {
        "id": "sentinel2_median",
        "name": "Sentinel-2 Cloud-Masked Median",
        "category": "Satellite Imagery",
        "asset_id": "COPERNICUS/S2_SR_HARMONIZED",
        "type": "ImageCollection",
        "target": "load",
        "bands": "B4,B3,B2",
        "min": 0,
        "max": 3000,
        "cloud_cover": 20,
        "description": "RGB median composite from Sentinel-2 surface reflectance.",
    },
    {
        "id": "landsat9_rgb",
        "name": "Landsat 9 Surface Reflectance RGB",
        "category": "Satellite Imagery",
        "asset_id": "LANDSAT/LC09/C02/T1_L2",
        "type": "ImageCollection",
        "target": "load",
        "bands": "SR_B4,SR_B3,SR_B2",
        "min": 0,
        "max": 30000,
        "cloud_cover": 20,
        "description": "Landsat 9 Collection 2 Level 2 RGB composite.",
    },
    {
        "id": "hls_s30_rgb",
        "name": "HLS Sentinel-2 RGB Composite",
        "category": "Satellite Imagery",
        "asset_id": "NASA/HLS/HLSS30/v002",
        "type": "ImageCollection",
        "target": "load",
        "bands": "B4,B3,B2",
        "min": 0,
        "max": 0.3,
        "cloud_cover": 20,
        "description": "Harmonized Landsat Sentinel-2 Sentinel-2 MSI true-color surface reflectance composite.",
    },
    {
        "id": "hls_l30_rgb",
        "name": "HLS Landsat RGB Composite",
        "category": "Satellite Imagery",
        "asset_id": "NASA/HLS/HLSL30/v002",
        "type": "ImageCollection",
        "target": "load",
        "bands": "B4,B3,B2",
        "min": 0,
        "max": 0.3,
        "cloud_cover": 20,
        "description": "Harmonized Landsat Sentinel-2 Landsat OLI true-color surface reflectance composite.",
    },
    {
        "id": "hls_s30_false_color",
        "name": "HLS Sentinel-2 False Color Vegetation",
        "category": "Vegetation Indices",
        "asset_id": "NASA/HLS/HLSS30/v002",
        "type": "ImageCollection",
        "target": "load",
        "bands": "B8A,B4,B3",
        "min": 0,
        "max": 0.4,
        "cloud_cover": 20,
        "description": "HLS Sentinel-2 near-infrared, red, and green composite for vegetation contrast.",
    },
    {
        "id": "hls_l30_false_color",
        "name": "HLS Landsat False Color Vegetation",
        "category": "Vegetation Indices",
        "asset_id": "NASA/HLS/HLSL30/v002",
        "type": "ImageCollection",
        "target": "load",
        "bands": "B5,B4,B3",
        "min": 0,
        "max": 0.4,
        "cloud_cover": 20,
        "description": "HLS Landsat near-infrared, red, and green composite for vegetation contrast.",
    },
    {
        "id": "hls_s30_swir_burn",
        "name": "HLS Sentinel-2 SWIR Burn/Water Composite",
        "category": "Fire",
        "asset_id": "NASA/HLS/HLSS30/v002",
        "type": "ImageCollection",
        "target": "load",
        "bands": "B12,B8A,B4",
        "min": 0,
        "max": 0.5,
        "cloud_cover": 20,
        "description": "HLS Sentinel-2 SWIR, NIR, and red composite useful for burn scars, moisture, and water mapping.",
    },
    {
        "id": "hls_l30_swir_burn",
        "name": "HLS Landsat SWIR Burn/Water Composite",
        "category": "Fire",
        "asset_id": "NASA/HLS/HLSL30/v002",
        "type": "ImageCollection",
        "target": "load",
        "bands": "B7,B5,B4",
        "min": 0,
        "max": 0.5,
        "cloud_cover": 20,
        "description": "HLS Landsat SWIR2, NIR, and red composite useful for burn scars, moisture, and water mapping.",
    },
    {
        "id": "hls_s30_reflectance_timeseries",
        "name": "HLS Sentinel-2 Reflectance Time Series",
        "category": "Satellite Imagery",
        "asset_id": "NASA/HLS/HLSS30/v002",
        "type": "ImageCollection",
        "target": "timeseries",
        "bands": "B2,B3,B4,B8A,B11,B12",
        "min": 0,
        "max": 0.5,
        "cloud_cover": 20,
        "description": "Pixel time-series setup for HLS Sentinel-2 visible, NIR, and SWIR reflectance bands.",
    },
    {
        "id": "hls_l30_reflectance_timeseries",
        "name": "HLS Landsat Reflectance Time Series",
        "category": "Satellite Imagery",
        "asset_id": "NASA/HLS/HLSL30/v002",
        "type": "ImageCollection",
        "target": "timeseries",
        "bands": "B2,B3,B4,B5,B6,B7",
        "min": 0,
        "max": 0.5,
        "cloud_cover": 20,
        "description": "Pixel time-series setup for HLS Landsat visible, NIR, and SWIR reflectance bands.",
    },
    {
        "id": "dynamic_world",
        "name": "Dynamic World Land Cover",
        "category": "Land Use & Land Cover",
        "asset_id": "GOOGLE/DYNAMICWORLD/V1",
        "type": "ImageCollection",
        "target": "load",
        "bands": "label",
        "min": 0,
        "max": 8,
        "palette": "419bdf,397d49,88b053,7a87c6,e49635,dfc35a,c4281b,a59b8f,b39fe1",
        "description": "Near-real-time 10 m land cover labels.",
    },
    {
        "id": "srtm_hillshade",
        "name": "SRTM Elevation",
        "category": "Elevation & Topography",
        "asset_id": "USGS/SRTMGL1_003",
        "type": "Image",
        "target": "load",
        "bands": "elevation",
        "min": 0,
        "max": 4000,
        "palette": "006400,7fff00,ffff00,ff8c00,8b4513,ffffff",
        "description": "Global 30 m elevation for terrain context.",
    },
    {
        "id": "modis_ndvi_timeseries",
        "name": "MODIS NDVI Time Series",
        "category": "Vegetation Indices",
        "asset_id": "MODIS/061/MOD13Q1",
        "type": "ImageCollection",
        "target": "timeseries",
        "bands": "NDVI",
        "min": 0,
        "max": 9000,
        "description": "16-day MODIS vegetation-index time series.",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _settings() -> QSettings:
    return QSettings()


def _read_json(key: str, default: Any) -> Any:
    raw = _settings().value(f"{SETTINGS_PREFIX}{key}", "", type=str)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _write_json(key: str, value: Any) -> None:
    _settings().setValue(f"{SETTINGS_PREFIX}{key}", json.dumps(value))


def dataset_summary(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact, settings-safe dataset record."""
    keys = (
        "id",
        "name",
        "title",
        "type",
        "source",
        "provider",
        "category",
        "description",
        "thumbnail",
        "url",
        "docs",
        "script",
        "sample_code",
        "start_date",
        "end_date",
        "keywords",
        "vis_params",
        "bigquery_table",
    )
    return {key: dataset.get(key) for key in keys if dataset.get(key) not in (None, "")}


def get_favorites() -> List[Dict[str, Any]]:
    return _read_json("favorites", [])


def is_favorite(asset_id: str) -> bool:
    return any(item.get("id") == asset_id for item in get_favorites())


def add_favorite(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    record = dataset_summary(dataset)
    if not record.get("id"):
        return get_favorites()
    record["favorited_at"] = _now_iso()
    favorites = [item for item in get_favorites() if item.get("id") != record["id"]]
    favorites.insert(0, record)
    _write_json("favorites", favorites)
    return favorites


def remove_favorite(asset_id: str) -> List[Dict[str, Any]]:
    favorites = [item for item in get_favorites() if item.get("id") != asset_id]
    _write_json("favorites", favorites)
    return favorites


def get_recents() -> List[Dict[str, Any]]:
    return _read_json("recent_datasets", [])


def record_recent_dataset(
    dataset: Dict[str, Any], action: str = "load"
) -> List[Dict[str, Any]]:
    record = dataset_summary(dataset)
    if not record.get("id"):
        return get_recents()
    record["last_action"] = action
    record["last_used_at"] = _now_iso()
    recents = [item for item in get_recents() if item.get("id") != record["id"]]
    recents.insert(0, record)
    recents = recents[:MAX_RECENTS]
    _write_json("recent_datasets", recents)
    return recents


def get_recipes() -> List[Dict[str, Any]]:
    custom = _read_json("custom_recipes", [])
    return DEFAULT_RECIPES + custom


def get_export_history() -> List[Dict[str, Any]]:
    return _read_json("export_history", [])


def record_export_job(
    job: Dict[str, Any], status: str, message: str = ""
) -> List[Dict[str, Any]]:
    record = dict(job)
    record["status"] = status
    record["message"] = message
    record["updated_at"] = _now_iso()
    history = get_export_history()
    history.insert(0, record)
    history = history[:MAX_EXPORT_HISTORY]
    _write_json("export_history", history)
    return history


def find_dataset_record(asset_id: str) -> Optional[Dict[str, Any]]:
    for collection in (get_favorites(), get_recents()):
        for item in collection:
            if item.get("id") == asset_id:
                return item
    return None
