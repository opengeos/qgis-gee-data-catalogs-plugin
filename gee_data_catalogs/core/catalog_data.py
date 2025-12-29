"""
GEE Data Catalog Data

This module provides data and functions for browsing the GEE Data Catalog.
Dynamically loads catalog data from official sources:
- Official GEE Catalog: https://github.com/opengeos/Earth-Engine-Catalog
- Awesome GEE Community Datasets: https://github.com/samapriya/awesome-gee-community-datasets
"""

import csv
import io
import json
import os
from typing import Any, Dict, List, Optional
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from qgis.core import QgsMessageLog, Qgis, QgsSettings

# URLs for catalog data
OFFICIAL_CATALOG_TSV_URL = "https://raw.githubusercontent.com/opengeos/Earth-Engine-Catalog/master/gee_catalog.tsv"
OFFICIAL_CATALOG_JSON_URL = "https://raw.githubusercontent.com/opengeos/Earth-Engine-Catalog/master/gee_catalog.json"
COMMUNITY_CATALOG_CSV_URL = "https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.csv"
COMMUNITY_CATALOG_JSON_URL = "https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.json"

# Cache for loaded catalogs
_catalog_cache = {
    "official": None,
    "community": None,
    "last_update": None,
}

# Default categories for organizing datasets
DEFAULT_CATEGORIES = [
    "Landsat",
    "Sentinel",
    "MODIS",
    "Elevation",
    "Land Cover",
    "Climate & Weather",
    "Boundaries",
    "Night Lights",
    "Population",
    "Water",
    "Vegetation",
    "Atmosphere",
    "Agriculture",
    "Soil",
    "Fire",
    "Ocean",
    "Urban",
    "Other",
]

# Keywords to category mapping
CATEGORY_KEYWORDS = {
    "Landsat": ["landsat", "usgs/landsat"],
    "Sentinel": [
        "sentinel",
        "copernicus/s1",
        "copernicus/s2",
        "copernicus/s3",
        "copernicus/s5",
    ],
    "MODIS": ["modis", "mod09", "mod11", "mod13", "mod14", "mod44", "mcd"],
    "Elevation": [
        "elevation",
        "dem",
        "srtm",
        "aster",
        "alos",
        "terrain",
        "topography",
        "bathymetry",
    ],
    "Land Cover": [
        "landcover",
        "land_cover",
        "land cover",
        "lulc",
        "worldcover",
        "nlcd",
        "globcover",
        "corine",
    ],
    "Climate & Weather": [
        "climate",
        "weather",
        "temperature",
        "precipitation",
        "era5",
        "chirps",
        "gpm",
        "trmm",
        "ecmwf",
    ],
    "Boundaries": [
        "boundary",
        "boundaries",
        "border",
        "admin",
        "gaul",
        "tiger",
        "gadm",
        "countries",
        "states",
    ],
    "Night Lights": [
        "nightlight",
        "night_light",
        "night light",
        "viirs",
        "dmsp",
        "lights",
    ],
    "Population": ["population", "demographic", "worldpop", "gpw", "landscan"],
    "Water": ["water", "hydrology", "flood", "river", "lake", "wetland", "gsw", "jrc"],
    "Vegetation": ["vegetation", "ndvi", "evi", "lai", "gpp", "npp", "forest", "tree"],
    "Atmosphere": [
        "atmosphere",
        "aerosol",
        "ozone",
        "no2",
        "co2",
        "methane",
        "air quality",
    ],
    "Agriculture": [
        "agriculture",
        "crop",
        "harvest",
        "cropland",
        "pasture",
        "irrigation",
    ],
    "Soil": ["soil", "sand", "clay", "carbon", "moisture", "organic"],
    "Fire": ["fire", "burn", "burned", "wildfire", "active fire"],
    "Ocean": ["ocean", "sea", "marine", "sst", "chlorophyll", "coral", "reef"],
    "Urban": ["urban", "built", "building", "impervious", "settlement"],
}


def _categorize_dataset(dataset: Dict) -> str:
    """Determine the category for a dataset based on keywords.

    Args:
        dataset: Dataset dictionary.

    Returns:
        Category name.
    """
    # Check id, title, and keywords
    search_text = " ".join(
        [
            str(dataset.get("id", "")).lower(),
            str(dataset.get("title", "")).lower(),
            str(dataset.get("name", "")).lower(),
            " ".join(
                dataset.get("keywords", [])
                if isinstance(dataset.get("keywords"), list)
                else str(dataset.get("keywords", "")).split(", ")
            ),
            str(dataset.get("tags", "")).lower(),
        ]
    )

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in search_text:
                return category

    return "Other"


def _parse_tsv_catalog(content: str) -> List[Dict]:
    """Parse TSV format catalog data.

    Args:
        content: TSV content string.

    Returns:
        List of dataset dictionaries.
    """
    datasets = []
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")

    for row in reader:
        # Skip deprecated datasets
        if row.get("deprecated", "").lower() == "true":
            continue

        dataset = {
            "id": row.get("id", ""),
            "name": row.get("title", row.get("id", "")),
            "title": row.get("title", ""),
            "type": _normalize_type(row.get("type", "")),
            "description": row.get("snippet", ""),
            "provider": row.get("provider", ""),
            "start_date": row.get("state_date", row.get("start_date", "")),
            "end_date": row.get("end_date", ""),
            "bbox": row.get("bbox", ""),
            "keywords": (
                row.get("keywords", "").split(", ") if row.get("keywords") else []
            ),
            "url": row.get("url", ""),
            "script": row.get("script", ""),
            "thumbnail": row.get("thumbnail", ""),
            "license": row.get("license", ""),
            "catalog_url": row.get("catalog", ""),
            "source": "official",
        }
        dataset["category"] = _categorize_dataset(dataset)
        datasets.append(dataset)

    return datasets


def _parse_json_catalog(content: str) -> List[Dict]:
    """Parse JSON format catalog data.

    Args:
        content: JSON content string.

    Returns:
        List of dataset dictionaries.
    """
    datasets = []
    try:
        data = json.loads(content)
        if isinstance(data, list):
            for item in data:
                # Skip deprecated datasets
                if item.get("deprecated", False):
                    continue

                dataset = {
                    "id": item.get("id", ""),
                    "name": item.get("title", item.get("id", "")),
                    "title": item.get("title", ""),
                    "type": _normalize_type(item.get("type", "")),
                    "description": item.get("snippet", item.get("description", "")),
                    "provider": item.get("provider", ""),
                    "start_date": item.get("start_date", item.get("state_date", "")),
                    "end_date": item.get("end_date", ""),
                    "bbox": item.get("bbox", ""),
                    "keywords": (
                        item.get("keywords", [])
                        if isinstance(item.get("keywords"), list)
                        else str(item.get("keywords", "")).split(", ")
                    ),
                    "url": item.get("url", ""),
                    "script": item.get("script", ""),
                    "thumbnail": item.get("thumbnail", ""),
                    "license": item.get("license", ""),
                    "catalog_url": item.get("catalog", ""),
                    "source": "official",
                }
                dataset["category"] = _categorize_dataset(dataset)
                datasets.append(dataset)
    except json.JSONDecodeError as e:
        QgsMessageLog.logMessage(
            f"Failed to parse JSON catalog: {e}", "GEE Data Catalogs", Qgis.Warning
        )

    return datasets


def _parse_community_csv(content: str) -> List[Dict]:
    """Parse community catalog CSV data.

    Args:
        content: CSV content string.

    Returns:
        List of dataset dictionaries.
    """
    datasets = []
    reader = csv.DictReader(io.StringIO(content))

    for row in reader:
        dataset = {
            "id": row.get("id", row.get("asset_id", row.get("ee_id_snippet", ""))),
            "name": row.get("title", row.get("name", row.get("id", ""))),
            "title": row.get("title", row.get("name", "")),
            "type": _normalize_type(row.get("type", row.get("gee_type", ""))),
            "description": row.get("description", row.get("snippet", "")),
            "provider": row.get("provider", row.get("source", "")),
            "start_date": row.get("start_date", ""),
            "end_date": row.get("end_date", ""),
            "keywords": (
                row.get("tags", row.get("keywords", "")).split(", ")
                if row.get("tags") or row.get("keywords")
                else []
            ),
            "url": row.get(
                "url", row.get("link", row.get("docs", row.get("sample_code", "")))
            ),
            "docs": row.get("docs", ""),
            "sample_code": row.get("sample_code", ""),
            "thumbnail": row.get("thumbnail", ""),
            "license": row.get("license", ""),
            "source": "community",
        }

        # Extract ID from snippet if needed
        if not dataset["id"] and row.get("ee_id_snippet"):
            snippet = row.get("ee_id_snippet", "")
            if "'" in snippet:
                parts = snippet.split("'")
                if len(parts) >= 2:
                    dataset["id"] = parts[1]

        if dataset["id"]:
            dataset["category"] = _categorize_dataset(dataset)
            datasets.append(dataset)

    return datasets


def _parse_community_json(content: str) -> List[Dict]:
    """Parse community catalog JSON data.

    Args:
        content: JSON content string.

    Returns:
        List of dataset dictionaries.
    """
    datasets = []
    try:
        data = json.loads(content)
        items = data if isinstance(data, list) else data.get("datasets", [])

        for item in items:
            dataset = {
                "id": item.get(
                    "id", item.get("asset_id", item.get("ee_id_snippet", ""))
                ),
                "name": item.get("title", item.get("name", item.get("id", ""))),
                "title": item.get("title", item.get("name", "")),
                "type": _normalize_type(item.get("type", item.get("gee_type", ""))),
                "description": item.get("description", item.get("snippet", "")),
                "provider": item.get("provider", item.get("source", "")),
                "start_date": item.get("start_date", ""),
                "end_date": item.get("end_date", ""),
                "keywords": (
                    item.get("tags", item.get("keywords", []))
                    if isinstance(item.get("tags", item.get("keywords")), list)
                    else str(item.get("tags", item.get("keywords", ""))).split(", ")
                ),
                "url": item.get(
                    "url",
                    item.get("link", item.get("docs", item.get("sample_code", ""))),
                ),
                "docs": item.get("docs", ""),
                "sample_code": item.get("sample_code", ""),
                "thumbnail": item.get("thumbnail", ""),
                "license": item.get("license", ""),
                "source": "community",
            }

            # Extract ID from snippet if needed
            if not dataset["id"] and item.get("ee_id_snippet"):
                snippet = str(item.get("ee_id_snippet", ""))
                if "'" in snippet:
                    parts = snippet.split("'")
                    if len(parts) >= 2:
                        dataset["id"] = parts[1]

            if dataset["id"]:
                dataset["category"] = _categorize_dataset(dataset)
                datasets.append(dataset)

    except json.JSONDecodeError as e:
        QgsMessageLog.logMessage(
            f"Failed to parse community JSON catalog: {e}",
            "GEE Data Catalogs",
            Qgis.Warning,
        )

    return datasets


def _normalize_type(type_str: str) -> str:
    """Normalize dataset type string.

    Args:
        type_str: Raw type string.

    Returns:
        Normalized type (Image, ImageCollection, FeatureCollection, Table).
    """
    type_lower = str(type_str).lower().replace("_", "").replace(" ", "")

    if "imagecollection" in type_lower:
        return "ImageCollection"
    elif "featurecollection" in type_lower or "table" in type_lower:
        return "FeatureCollection"
    elif "image" in type_lower:
        return "Image"
    else:
        return "Image"  # Default


def fetch_official_catalog(use_cache: bool = True) -> List[Dict]:
    """Fetch the official GEE catalog from GitHub.

    Args:
        use_cache: Whether to use cached data if available.

    Returns:
        List of dataset dictionaries.
    """
    global _catalog_cache

    if use_cache and _catalog_cache["official"] is not None:
        return _catalog_cache["official"]

    datasets = []

    # Try JSON first, then TSV
    for url, parser in [
        (OFFICIAL_CATALOG_JSON_URL, _parse_json_catalog),
        (OFFICIAL_CATALOG_TSV_URL, _parse_tsv_catalog),
    ]:
        try:
            QgsMessageLog.logMessage(
                f"Fetching official catalog from: {url}", "GEE Data Catalogs", Qgis.Info
            )
            with urlopen(url, timeout=30) as response:
                content = response.read().decode("utf-8")
                datasets = parser(content)
                if datasets:
                    QgsMessageLog.logMessage(
                        f"Loaded {len(datasets)} datasets from official catalog",
                        "GEE Data Catalogs",
                        Qgis.Info,
                    )
                    _catalog_cache["official"] = datasets
                    return datasets
        except (HTTPError, URLError) as e:
            QgsMessageLog.logMessage(
                f"Failed to fetch from {url}: {e}", "GEE Data Catalogs", Qgis.Warning
            )
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error parsing catalog from {url}: {e}",
                "GEE Data Catalogs",
                Qgis.Warning,
            )

    return datasets


def fetch_community_catalog(use_cache: bool = True) -> List[Dict]:
    """Fetch the awesome GEE community catalog from GitHub.

    Args:
        use_cache: Whether to use cached data if available.

    Returns:
        List of dataset dictionaries.
    """
    global _catalog_cache

    if use_cache and _catalog_cache["community"] is not None:
        return _catalog_cache["community"]

    datasets = []

    # Try JSON first, then CSV
    for url, parser in [
        (COMMUNITY_CATALOG_JSON_URL, _parse_community_json),
        (COMMUNITY_CATALOG_CSV_URL, _parse_community_csv),
    ]:
        try:
            QgsMessageLog.logMessage(
                f"Fetching community catalog from: {url}",
                "GEE Data Catalogs",
                Qgis.Info,
            )
            with urlopen(url, timeout=30) as response:
                content = response.read().decode("utf-8")
                datasets = parser(content)
                if datasets:
                    QgsMessageLog.logMessage(
                        f"Loaded {len(datasets)} datasets from community catalog",
                        "GEE Data Catalogs",
                        Qgis.Info,
                    )
                    _catalog_cache["community"] = datasets
                    return datasets
        except (HTTPError, URLError) as e:
            QgsMessageLog.logMessage(
                f"Failed to fetch from {url}: {e}", "GEE Data Catalogs", Qgis.Warning
            )
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error parsing catalog from {url}: {e}",
                "GEE Data Catalogs",
                Qgis.Warning,
            )

    return datasets


def get_all_datasets(
    include_community: bool = True, use_cache: bool = True
) -> List[Dict]:
    """Get all datasets from both official and community catalogs.

    Args:
        include_community: Whether to include community datasets.
        use_cache: Whether to use cached data if available.

    Returns:
        List of all dataset dictionaries.
    """
    all_datasets = []

    # Fetch official catalog
    official = fetch_official_catalog(use_cache=use_cache)
    all_datasets.extend(official)

    # Fetch community catalog
    if include_community:
        community = fetch_community_catalog(use_cache=use_cache)
        # Avoid duplicates by ID
        existing_ids = {d["id"] for d in all_datasets}
        for dataset in community:
            if dataset["id"] not in existing_ids:
                all_datasets.append(dataset)

    return all_datasets


def get_catalog_data(include_community: bool = True, use_cache: bool = True) -> Dict:
    """Get catalog data organized by category.

    Args:
        include_community: Whether to include community datasets.
        use_cache: Whether to use cached data if available.

    Returns:
        Dictionary containing datasets organized by category.
    """
    datasets = get_all_datasets(
        include_community=include_community, use_cache=use_cache
    )

    # Organize by category
    catalog = {}
    for category in DEFAULT_CATEGORIES:
        catalog[category] = {
            "description": f"{category} datasets",
            "datasets": [],
        }

    for dataset in datasets:
        category = dataset.get("category", "Other")
        if category not in catalog:
            catalog[category] = {"description": f"{category} datasets", "datasets": []}
        catalog[category]["datasets"].append(dataset)

    # Sort datasets within each category by name
    for category in catalog:
        catalog[category]["datasets"].sort(key=lambda x: x.get("name", "").lower())

    return catalog


def get_categories() -> List[str]:
    """Get list of dataset categories.

    Returns:
        List of category names.
    """
    return DEFAULT_CATEGORIES.copy()


def get_datasets_by_category(
    category: str, include_community: bool = True
) -> List[Dict]:
    """Get datasets for a specific category.

    Args:
        category: Category name.
        include_community: Whether to include community datasets.

    Returns:
        List of dataset dictionaries.
    """
    catalog = get_catalog_data(include_community=include_community)
    cat_data = catalog.get(category, {})
    return cat_data.get("datasets", [])


def search_datasets(
    query: str = "",
    category: Optional[str] = None,
    data_type: Optional[str] = None,
    provider: Optional[str] = None,
    source: Optional[str] = None,
    include_community: bool = True,
) -> List[Dict]:
    """Search datasets by various criteria.

    Args:
        query: Search query string (matches name, description, tags).
        category: Filter by category.
        data_type: Filter by data type (Image, ImageCollection, FeatureCollection).
        provider: Filter by provider.
        source: Filter by source ("official" or "community").
        include_community: Whether to include community datasets.

    Returns:
        List of matching dataset dictionaries.
    """
    datasets = get_all_datasets(include_community=include_community)
    results = []
    query_lower = query.lower().strip()

    for dataset in datasets:
        # Check category filter
        if category and dataset.get("category") != category:
            continue

        # Check data type filter
        if data_type and dataset.get("type") != data_type:
            continue

        # Check provider filter
        if (
            provider
            and provider.lower() not in str(dataset.get("provider", "")).lower()
        ):
            continue

        # Check source filter
        if source and dataset.get("source") != source:
            continue

        # Check query match
        if query_lower:
            matches = False
            search_fields = [
                str(dataset.get("name", "")).lower(),
                str(dataset.get("title", "")).lower(),
                str(dataset.get("description", "")).lower(),
                str(dataset.get("id", "")).lower(),
            ]
            # Add keywords
            keywords = dataset.get("keywords", [])
            if isinstance(keywords, list):
                search_fields.extend([k.lower() for k in keywords])
            else:
                search_fields.append(str(keywords).lower())

            for field in search_fields:
                if query_lower in field:
                    matches = True
                    break

            if not matches:
                continue

        results.append(dataset)

    return results


def get_dataset_info(dataset_id: str, include_community: bool = True) -> Optional[Dict]:
    """Get detailed information for a specific dataset.

    Args:
        dataset_id: The dataset ID.
        include_community: Whether to search community datasets.

    Returns:
        Dataset dictionary or None if not found.
    """
    datasets = get_all_datasets(include_community=include_community)
    for dataset in datasets:
        if dataset.get("id") == dataset_id:
            return dataset
    return None


def get_providers(include_community: bool = True) -> List[str]:
    """Get list of all unique providers.

    Args:
        include_community: Whether to include community datasets.

    Returns:
        List of provider names.
    """
    datasets = get_all_datasets(include_community=include_community)
    providers = set()
    for dataset in datasets:
        provider = dataset.get("provider", "").strip()
        if provider:
            providers.add(provider)
    return sorted(list(providers))


def get_tags(include_community: bool = True) -> List[str]:
    """Get list of all unique tags.

    Args:
        include_community: Whether to include community datasets.

    Returns:
        List of tag names.
    """
    datasets = get_all_datasets(include_community=include_community)
    tags = set()
    for dataset in datasets:
        keywords = dataset.get("keywords", [])
        if isinstance(keywords, list):
            for tag in keywords:
                if tag:
                    tags.add(tag.strip())
        elif keywords:
            for tag in str(keywords).split(","):
                if tag.strip():
                    tags.add(tag.strip())
    return sorted(list(tags))


def clear_cache():
    """Clear the catalog cache."""
    global _catalog_cache
    _catalog_cache = {
        "official": None,
        "community": None,
        "last_update": None,
    }
    QgsMessageLog.logMessage("Catalog cache cleared", "GEE Data Catalogs", Qgis.Info)


def refresh_catalogs() -> Dict:
    """Refresh catalogs from remote sources.

    Returns:
        Dictionary with counts of loaded datasets.
    """
    clear_cache()

    official = fetch_official_catalog(use_cache=False)
    community = fetch_community_catalog(use_cache=False)

    return {
        "official_count": len(official),
        "community_count": len(community),
        "total_count": len(official) + len(community),
    }
