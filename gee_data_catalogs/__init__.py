"""
GEE Data Catalogs Plugin for QGIS

A plugin for browsing, searching, and loading Google Earth Engine
data catalogs directly in QGIS.
"""

from .gee_data_catalogs import GeeDataCatalogs


def classFactory(iface):
    """Load GeeDataCatalogs class from file gee_data_catalogs.

    Args:
        iface: A QGIS interface instance.

    Returns:
        GeeDataCatalogs: The plugin instance.
    """
    return GeeDataCatalogs(iface)
