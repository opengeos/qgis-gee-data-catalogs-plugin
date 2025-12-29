"""
Earth Engine Utilities for GEE Data Catalogs

This module provides utility functions for working with Earth Engine in QGIS.
"""

import os
from typing import Any, Dict, List, Optional

try:
    import ee
except ImportError:
    ee = None

from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsMessageLog,
    Qgis,
)


# Track if EE has been initialized
_ee_initialized = False

# Global registry to track EE layers for Inspector
_ee_layer_registry = {}


def is_ee_initialized() -> bool:
    """Check if Earth Engine has been initialized."""
    global _ee_initialized
    return _ee_initialized


def initialize_ee(project: str = None, credentials: Any = None) -> bool:
    """Initialize Earth Engine.

    Args:
        project: Google Cloud project ID.
        credentials: Optional credentials object.

    Returns:
        True if initialization was successful, False otherwise.
    """
    global _ee_initialized

    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    if project is None or project == "":
        project = os.environ.get("EE_PROJECT_ID", None)

    try:
        if project:
            ee.Initialize(credentials=credentials, project=project)
        else:
            ee.Initialize(credentials=credentials)
        _ee_initialized = True
        return True
    except Exception as e:
        # Try to authenticate first
        try:
            ee.Authenticate()
            if project:
                ee.Initialize(credentials=credentials, project=project)
            else:
                ee.Initialize(credentials=credentials)
            _ee_initialized = True
            return True
        except Exception as auth_e:
            raise RuntimeError(
                f"Failed to initialize Earth Engine: {e}\n"
                f"Authentication also failed: {auth_e}"
            )


def try_auto_initialize_ee() -> bool:
    """Try to auto-initialize Earth Engine if EE_PROJECT_ID is set.

    Returns:
        True if initialization was successful, False otherwise.
    """
    global _ee_initialized

    if _ee_initialized:
        return True

    if ee is None:
        return False

    project = os.environ.get("EE_PROJECT_ID", None)
    if not project:
        return False

    try:
        ee.Initialize(project=project)
        _ee_initialized = True
        QgsMessageLog.logMessage(
            f"Earth Engine auto-initialized with project: {project}",
            "GEE Data Catalogs",
            Qgis.Info,
        )
        return True
    except Exception as e:
        QgsMessageLog.logMessage(
            f"Failed to auto-initialize Earth Engine: {e}",
            "GEE Data Catalogs",
            Qgis.Warning,
        )
        return False


def get_ee_tile_url(
    ee_object: Any,
    vis_params: Optional[Dict] = None,
) -> str:
    """Get an XYZ tile URL for an Earth Engine object.

    Args:
        ee_object: An Earth Engine Image or ImageCollection.
        vis_params: Visualization parameters dictionary.

    Returns:
        XYZ tile URL string.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    vis_params = vis_params or {}

    # Handle ImageCollection by taking the first image or mosaic
    if isinstance(ee_object, ee.ImageCollection):
        ee_object = ee_object.mosaic()

    # Get the map ID
    map_id_dict = ee_object.getMapId(vis_params)

    # Construct the tile URL
    tile_url = map_id_dict.get("tile_fetcher").url_format

    return tile_url


def add_ee_layer(
    ee_object: Any,
    vis_params: Optional[Dict] = None,
    name: str = "EE Layer",
    shown: bool = True,
    opacity: float = 1.0,
) -> QgsRasterLayer:
    """Add an Earth Engine layer to the QGIS map.

    Args:
        ee_object: An Earth Engine Image, ImageCollection, or FeatureCollection.
        vis_params: Visualization parameters dictionary.
        name: Name for the layer.
        shown: Whether the layer should be visible.
        opacity: Layer opacity (0.0 to 1.0).

    Returns:
        QgsRasterLayer instance.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    vis_params = vis_params or {}

    # Save current map extent to preserve it
    from qgis.utils import iface

    current_extent = None
    if iface and iface.mapCanvas():
        current_extent = iface.mapCanvas().extent()

    # Try to use qgis_geemap if available
    try:
        from qgis_geemap.core.qgis_map import Map

        m = Map()
        layer = m.add_layer(ee_object, vis_params, name, shown, opacity)

        # Restore the map extent after qgis_geemap adds the layer
        if current_extent and iface and iface.mapCanvas():
            iface.mapCanvas().setExtent(current_extent)
            iface.mapCanvas().refresh()

        # Register the layer for Inspector (important: register before returning)
        add_ee_layer_to_registry(name, ee_object, vis_params)

        return layer
    except ImportError:
        pass

    # Fallback: Handle different EE object types
    if isinstance(ee_object, (ee.Image, ee.ImageCollection)):
        tile_url = get_ee_tile_url(ee_object, vis_params)
        uri = f"type=xyz&url={tile_url}&zmax=24&zmin=0"
        layer = QgsRasterLayer(uri, name, "wms")
    elif isinstance(ee_object, ee.FeatureCollection):
        # For FeatureCollection, render as styled tiles
        # Filter out params not supported by FeatureCollection.style()
        # style() accepts: color, pointSize, pointShape, width, fillColor, styleProperty, neighborhood, lineType
        valid_style_keys = {
            "color",
            "pointSize",
            "pointShape",
            "width",
            "fillColor",
            "styleProperty",
            "neighborhood",
            "lineType",
        }
        style_params = {k: v for k, v in vis_params.items() if k in valid_style_keys}

        styled_fc = ee_object
        if style_params:
            styled_fc = ee_object.style(**style_params)
        tile_url = get_ee_tile_url(styled_fc, {})
        uri = f"type=xyz&url={tile_url}&zmax=24&zmin=0"
        layer = QgsRasterLayer(uri, name, "wms")
    else:
        raise TypeError(f"Unsupported Earth Engine object type: {type(ee_object)}")

    if not layer.isValid():
        raise ValueError(f"Failed to create valid layer: {name}")

    # Set opacity
    if hasattr(layer, "renderer") and layer.renderer():
        layer.renderer().setOpacity(opacity)

    # Add to project (False = don't add to legend first, we'll add manually)
    project = QgsProject.instance()
    project.addMapLayer(layer, False)

    # Add to legend at top
    root = project.layerTreeRoot()
    root.insertLayer(0, layer)

    # Set visibility
    layer_tree = project.layerTreeRoot().findLayer(layer.id())
    if layer_tree:
        layer_tree.setItemVisibilityChecked(shown)

    # Restore the map extent after adding the layer
    if current_extent and iface and iface.mapCanvas():
        iface.mapCanvas().setExtent(current_extent)
        iface.mapCanvas().refresh()

    # Register the layer for Inspector
    add_ee_layer_to_registry(name, ee_object, vis_params)

    return layer


def get_ee_layers() -> Dict:
    """Get the registry of Earth Engine layers.

    Returns:
        Dictionary mapping layer names to (ee_object, vis_params) tuples.
    """
    global _ee_layer_registry
    return _ee_layer_registry.copy()


def add_ee_layer_to_registry(
    name: str, ee_object: Any, vis_params: Optional[Dict] = None
):
    """Add an Earth Engine layer to the registry for Inspector.

    Args:
        name: Layer name.
        ee_object: Earth Engine object.
        vis_params: Visualization parameters.
    """
    global _ee_layer_registry
    _ee_layer_registry[name] = (ee_object, vis_params or {})


def remove_ee_layer_from_registry(name: str):
    """Remove an Earth Engine layer from the registry.

    Args:
        name: Layer name to remove.
    """
    global _ee_layer_registry
    _ee_layer_registry.pop(name, None)


def clear_ee_layer_registry():
    """Clear all layers from the registry."""
    global _ee_layer_registry
    _ee_layer_registry = {}


def detect_asset_type(asset_id: str) -> str:
    """Detect the type of an Earth Engine asset.

    Args:
        asset_id: The asset ID to check.

    Returns:
        One of: "Image", "ImageCollection", "FeatureCollection", "Table", or "Unknown"
    """
    if ee is None:
        raise ImportError("Earth Engine API not available")

    # Try Image first
    try:
        image = ee.Image(asset_id)
        # Try to get a property to verify it's actually an Image
        image.bandNames().getInfo()
        return "Image"
    except Exception as img_err:
        # Check if error indicates it's not an Image
        img_error_str = str(img_err).lower()
        if "imagecollection" in img_error_str:
            return "ImageCollection"
        if "featurecollection" in img_error_str or "table" in img_error_str:
            return "FeatureCollection"

    # Try ImageCollection
    try:
        collection = ee.ImageCollection(asset_id)
        # Try to get size to verify
        collection.size().getInfo()
        return "ImageCollection"
    except Exception as ic_err:
        ic_error_str = str(ic_err).lower()
        if "image" in ic_error_str and "imagecollection" not in ic_error_str:
            return "Image"
        if "featurecollection" in ic_error_str or "table" in ic_error_str:
            return "FeatureCollection"

    # Try FeatureCollection
    try:
        fc = ee.FeatureCollection(asset_id)
        fc.size().getInfo()
        return "FeatureCollection"
    except Exception:
        pass

    return "Unknown"


def load_ee_asset(asset_id: str, asset_type: str = None) -> Any:
    """Load an Earth Engine asset with the correct type.

    Args:
        asset_id: The asset ID to load.
        asset_type: Optional type hint ("Image", "ImageCollection", "FeatureCollection").
                    If not provided, type will be auto-detected.

    Returns:
        The loaded Earth Engine object (ee.Image, ee.ImageCollection, or ee.FeatureCollection).
    """
    if ee is None:
        raise ImportError("Earth Engine API not available")

    if asset_type is None:
        asset_type = detect_asset_type(asset_id)

    if asset_type == "Image":
        return ee.Image(asset_id)
    elif asset_type == "ImageCollection":
        return ee.ImageCollection(asset_id)
    elif asset_type == "FeatureCollection":
        return ee.FeatureCollection(asset_id)
    else:
        # Default to trying Image, then ImageCollection, then FeatureCollection
        for loader, name in [
            (ee.Image, "Image"),
            (ee.ImageCollection, "ImageCollection"),
            (ee.FeatureCollection, "FeatureCollection"),
        ]:
            try:
                obj = loader(asset_id)
                # Verify it works
                if name == "Image":
                    obj.bandNames().getInfo()
                else:
                    obj.size().getInfo()
                return obj
            except Exception:
                continue
        raise ValueError(f"Could not load asset: {asset_id}")


def filter_image_collection(
    collection: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    cloud_cover: Optional[float] = None,
    cloud_property: str = "CLOUDY_PIXEL_PERCENTAGE",
) -> Any:
    """Filter an ImageCollection by date, bounds, and cloud cover.

    Args:
        collection: An Earth Engine ImageCollection.
        start_date: Start date string (YYYY-MM-DD).
        end_date: End date string (YYYY-MM-DD).
        bbox: Bounding box as [west, south, east, north].
        cloud_cover: Maximum cloud cover percentage (0-100).
        cloud_property: Name of the cloud cover property.

    Returns:
        Filtered ImageCollection.
    """
    if ee is None:
        raise ImportError("Earth Engine API not available")

    filtered = collection

    # Filter by date
    if start_date and end_date:
        filtered = filtered.filterDate(start_date, end_date)
    elif start_date:
        filtered = filtered.filterDate(start_date, "2099-12-31")
    elif end_date:
        filtered = filtered.filterDate("1970-01-01", end_date)

    # Filter by bounds
    if bbox and len(bbox) == 4:
        geometry = ee.Geometry.Rectangle(bbox)
        filtered = filtered.filterBounds(geometry)

    # Filter by cloud cover
    if cloud_cover is not None:
        filtered = filtered.filter(ee.Filter.lt(cloud_property, cloud_cover))

    return filtered
