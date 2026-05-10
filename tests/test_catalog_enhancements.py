import json

from gee_data_catalogs.core import catalog_data, user_state
from gee_data_catalogs.dialogs.catalog_dock import CatalogDockWidget


def test_search_datasets_ranks_exact_and_weighted_matches(monkeypatch):
    datasets = [
        {
            "id": "COMMUNITY/S2_MISC",
            "name": "Miscellaneous optical imagery",
            "description": "Mentions sentinel in passing",
            "type": "ImageCollection",
            "source": "community",
            "keywords": [],
        },
        {
            "id": "COPERNICUS/S2_SR_HARMONIZED",
            "name": "Sentinel-2 MSI: MultiSpectral Instrument, Level-2A",
            "description": "Surface reflectance",
            "type": "ImageCollection",
            "source": "official",
            "keywords": ["sentinel", "surface reflectance"],
        },
    ]
    monkeypatch.setattr(
        catalog_data, "get_all_datasets", lambda include_community=True: datasets
    )

    results = catalog_data.search_datasets(query="sentinel surface reflectance")

    assert results[0]["id"] == "COPERNICUS/S2_SR_HARMONIZED"
    assert results[0]["_search_score"] > results[1]["_search_score"]


class _FakeSettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default="", type=str):
        value = self.values.get(key, default)
        if type is bool:
            return bool(value)
        if type is int:
            return int(value)
        return value

    def setValue(self, key, value):
        self.values[key] = value


def test_favorites_and_recents_are_persisted_as_compact_records(monkeypatch):
    settings = _FakeSettings()
    monkeypatch.setattr(user_state, "_settings", lambda: settings)

    dataset = {
        "id": "USGS/SRTMGL1_003",
        "name": "SRTM",
        "type": "Image",
        "source": "official",
        "description": "Elevation",
        "thumbnail": "https://example.com/thumb.png",
        "unused": "not persisted",
    }

    user_state.add_favorite(dataset)
    user_state.record_recent_dataset(dataset, "load")

    assert user_state.is_favorite("USGS/SRTMGL1_003")
    assert user_state.get_favorites()[0]["name"] == "SRTM"
    assert user_state.get_favorites()[0]["thumbnail"] == "https://example.com/thumb.png"
    assert "unused" not in user_state.get_favorites()[0]
    assert user_state.get_recents()[0]["last_action"] == "load"

    raw = settings.values["GeeDataCatalogs/favorites"]
    assert json.loads(raw)[0]["id"] == "USGS/SRTMGL1_003"

    user_state.remove_favorite("USGS/SRTMGL1_003")

    assert not user_state.is_favorite("USGS/SRTMGL1_003")
    assert user_state.get_favorites() == []


def test_saved_dataset_info_html_includes_thumbnail_placeholder():
    html = CatalogDockWidget._dataset_info_html(
        None,
        {
            "id": "USGS/SRTMGL1_003",
            "name": "SRTM",
            "type": "Image",
            "source": "official",
            "thumbnail": "https://example.com/thumb.png",
        },
    )

    assert "saved-thumbnail-placeholder" in html


def test_default_recipes_include_hls_workflows():
    recipes = {recipe["id"]: recipe for recipe in user_state.DEFAULT_RECIPES}

    assert recipes["hls_s30_rgb"]["asset_id"] == "NASA/HLS/HLSS30/v002"
    assert recipes["hls_l30_rgb"]["asset_id"] == "NASA/HLS/HLSL30/v002"
    assert recipes["hls_s30_reflectance_timeseries"]["target"] == "timeseries"
    assert recipes["hls_l30_reflectance_timeseries"]["bands"] == "B2,B3,B4,B5,B6,B7"
