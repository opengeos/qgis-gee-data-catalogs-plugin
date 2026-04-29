import sys
import types

from gee_data_catalogs.core import ee_utils


def test_add_ee_layer_falls_back_when_qgis_geemap_returns_invalid(monkeypatch):
    created_layers = []
    added_layers = []
    inserted_layers = []
    removed_layers = []

    class _FakeLayer:
        def __init__(self, uri="", name="", provider="", valid=True):
            self.uri = uri
            self._name = name
            self.provider = provider
            self._valid = valid
            self.custom_properties = {}

        def isValid(self):
            return self._valid

        def id(self):
            return self._name or "layer-id"

        def name(self):
            return self._name

        def renderer(self):
            return None

        def setCustomProperty(self, key, value):
            self.custom_properties[key] = value

    class _QgsRasterLayer(_FakeLayer):
        def __init__(self, uri="", name="", provider=""):
            super().__init__(uri, name, provider, valid=True)
            created_layers.append(self)

    class _InvalidGeemapLayer(_FakeLayer):
        def __init__(self):
            super().__init__(valid=False)

    class _LayerTreeRoot:
        def insertLayer(self, index, layer):
            inserted_layers.append((index, layer))

        def findLayer(self, layer_id):
            return None

    class _Project:
        def mapLayersByName(self, name):
            return []

        def removeMapLayer(self, layer_id):
            removed_layers.append(layer_id)

        def addMapLayer(self, layer, add_to_legend):
            added_layers.append((layer, add_to_legend))

        def layerTreeRoot(self):
            return _LayerTreeRoot()

    class _QgsProject:
        @staticmethod
        def instance():
            return _Project()

    class _FakeImage:
        def getMapId(self, vis_params):
            return {
                "tile_fetcher": types.SimpleNamespace(
                    url_format=("https://example.com/{z}/{x}/{y}?token=abc&expires=123")
                )
            }

        def get(self, key):
            raise RuntimeError("no asset id")

    class _FakeImageCollection:
        pass

    class _FakeFeatureCollection:
        pass

    class _FakeMap:
        def add_layer(self, ee_object, vis_params, name, shown, opacity):
            return _InvalidGeemapLayer()

    ee_module = types.SimpleNamespace(
        Image=_FakeImage,
        ImageCollection=_FakeImageCollection,
        FeatureCollection=_FakeFeatureCollection,
        serializer=types.SimpleNamespace(toJSON=lambda obj: "{}"),
    )
    qgis_geemap_module = types.ModuleType("qgis_geemap.core.qgis_map")
    qgis_geemap_module.Map = _FakeMap

    monkeypatch.setattr(ee_utils, "ee", ee_module)
    monkeypatch.setattr(ee_utils, "QgsRasterLayer", _QgsRasterLayer)
    monkeypatch.setattr(ee_utils, "QgsProject", _QgsProject)
    monkeypatch.setitem(sys.modules, "qgis_geemap", types.ModuleType("qgis_geemap"))
    monkeypatch.setitem(
        sys.modules, "qgis_geemap.core", types.ModuleType("qgis_geemap.core")
    )
    monkeypatch.setitem(sys.modules, "qgis_geemap.core.qgis_map", qgis_geemap_module)

    layer = ee_utils.add_ee_layer(_FakeImage(), {"min": 0, "max": 1}, "DSWx")

    assert layer is created_layers[0]
    expected_uri = (
        "type=xyz&url=https://example.com/{z}/{x}/{y}"
        "%3Ftoken%3Dabc%26expires%3D123&zmax=24&zmin=0"
    )
    assert layer.uri == expected_uri
    assert added_layers == [(layer, False)]
    assert inserted_layers == [(0, layer)]
    assert removed_layers == []
