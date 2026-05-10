"""QGIS Processing provider for repeatable Earth Engine catalog workflows."""

from __future__ import annotations

import json

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingProvider,
)
from qgis.PyQt.QtCore import QCoreApplication


def tr(text: str) -> str:
    return QCoreApplication.translate("GeeDataCatalogsProcessing", text)


class SearchCatalogAlgorithm(QgsProcessingAlgorithm):
    QUERY = "QUERY"
    CATEGORY = "CATEGORY"
    DATA_TYPE = "DATA_TYPE"
    SOURCE = "SOURCE"
    OUTPUT = "OUTPUT"

    TYPES = ["Any", "Image", "ImageCollection", "FeatureCollection", "BigQueryTable"]
    SOURCES = ["Any", "official", "community"]

    def name(self):
        return "search_catalog"

    def displayName(self):
        return tr("Search Earth Engine catalog")

    def group(self):
        return tr("Catalog")

    def groupId(self):
        return "catalog"

    def shortHelpString(self):
        return tr(
            "Search the configured Earth Engine catalogs and write matching datasets to JSON."
        )

    def createInstance(self):
        return SearchCatalogAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterString(
                self.QUERY, tr("Search query"), "", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.CATEGORY, tr("Category"), "", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.DATA_TYPE, tr("Data type"), self.TYPES, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SOURCE, tr("Source"), self.SOURCES, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                tr("Output JSON"),
                tr("JSON files (*.json)"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from .core.catalog_data import search_datasets

        query = self.parameterAsString(parameters, self.QUERY, context)
        category = self.parameterAsString(parameters, self.CATEGORY, context) or None
        type_index = self.parameterAsEnum(parameters, self.DATA_TYPE, context)
        source_index = self.parameterAsEnum(parameters, self.SOURCE, context)
        data_type = None if type_index == 0 else self.TYPES[type_index]
        source = None if source_index == 0 else self.SOURCES[source_index]
        output = self.parameterAsFileOutput(parameters, self.OUTPUT, context)

        results = search_datasets(
            query=query, category=category, data_type=data_type, source=source
        )
        with open(output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        feedback.pushInfo(tr(f"Wrote {len(results)} result(s) to {output}"))
        return {self.OUTPUT: output}


class GenerateSnippetAlgorithm(QgsProcessingAlgorithm):
    ASSET_ID = "ASSET_ID"
    ASSET_TYPE = "ASSET_TYPE"
    BANDS = "BANDS"
    VIS_MIN = "VIS_MIN"
    VIS_MAX = "VIS_MAX"
    PALETTE = "PALETTE"
    OUTPUT = "OUTPUT"

    TYPES = ["Image", "ImageCollection", "FeatureCollection"]

    def name(self):
        return "generate_python_snippet"

    def displayName(self):
        return tr("Generate Earth Engine Python snippet")

    def group(self):
        return tr("Code")

    def groupId(self):
        return "code"

    def createInstance(self):
        return GenerateSnippetAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(self.ASSET_ID, tr("Asset ID")))
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ASSET_TYPE, tr("Asset type"), self.TYPES, defaultValue=1
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.BANDS, tr("Bands (comma-separated)"), "", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.VIS_MIN, tr("Visualization min"), "", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.VIS_MAX, tr("Visualization max"), "", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.PALETTE, tr("Palette (comma-separated)"), "", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                tr("Output Python file"),
                tr("Python files (*.py)"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        asset_id = self.parameterAsString(parameters, self.ASSET_ID, context).strip()
        if not asset_id:
            raise QgsProcessingException(tr("Asset ID is required."))
        asset_type = self.TYPES[
            self.parameterAsEnum(parameters, self.ASSET_TYPE, context)
        ]
        output = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        bands = self.parameterAsString(parameters, self.BANDS, context).strip()
        vis_min = self.parameterAsString(parameters, self.VIS_MIN, context).strip()
        vis_max = self.parameterAsString(parameters, self.VIS_MAX, context).strip()
        palette = self.parameterAsString(parameters, self.PALETTE, context).strip()

        vis = {}
        if bands:
            vis["bands"] = [band.strip() for band in bands.split(",") if band.strip()]
        if vis_min:
            vis["min"] = float(vis_min) if "." in vis_min else int(vis_min)
        if vis_max:
            vis["max"] = float(vis_max) if "." in vis_max else int(vis_max)
        if palette:
            vis["palette"] = [
                color.strip() for color in palette.split(",") if color.strip()
            ]

        constructor = {
            "Image": "ee.Image",
            "ImageCollection": "ee.ImageCollection",
            "FeatureCollection": "ee.FeatureCollection",
        }[asset_type]
        layer_expr = "asset.mosaic()" if asset_type == "ImageCollection" else "asset"
        code = "\n".join(
            [
                "import ee",
                "from gee_data_catalogs.core.ee_utils import add_ee_layer",
                "",
                "# ee.Initialize(project='your-project-id')",
                f"asset = {constructor}({asset_id!r})",
                f"vis_params = {vis!r}",
                f"add_ee_layer({layer_expr}, vis_params, {asset_id.split('/')[-1]!r})",
                "",
            ]
        )
        with open(output, "w", encoding="utf-8") as f:
            f.write(code)
        feedback.pushInfo(tr(f"Wrote snippet to {output}"))
        return {self.OUTPUT: output}


class LoadAssetAlgorithm(QgsProcessingAlgorithm):
    ASSET_ID = "ASSET_ID"
    ASSET_TYPE = "ASSET_TYPE"
    NAME = "NAME"
    MOSAIC_COLLECTION = "MOSAIC_COLLECTION"
    OPACITY = "OPACITY"
    OUTPUT_NAME = "OUTPUT_NAME"

    TYPES = ["Auto", "Image", "ImageCollection", "FeatureCollection"]

    def name(self):
        return "load_asset"

    def displayName(self):
        return tr("Load Earth Engine asset")

    def group(self):
        return tr("Layers")

    def groupId(self):
        return "layers"

    def createInstance(self):
        return LoadAssetAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(self.ASSET_ID, tr("Asset ID")))
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ASSET_TYPE, tr("Asset type"), self.TYPES, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterString(self.NAME, tr("Layer name"), "", optional=True)
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.MOSAIC_COLLECTION, tr("Mosaic ImageCollections"), True
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.OPACITY,
                tr("Opacity"),
                QgsProcessingParameterNumber.Double,
                defaultValue=1.0,
                minValue=0.0,
                maxValue=1.0,
            )
        )
        self.addOutput(
            QgsProcessingOutputString(self.OUTPUT_NAME, tr("Loaded layer name"))
        )

    def processAlgorithm(self, parameters, context, feedback):
        import ee

        from .core.ee_utils import (
            add_ee_layer,
            detect_asset_type,
            initialize_ee,
            is_ee_initialized,
        )

        asset_id = self.parameterAsString(parameters, self.ASSET_ID, context).strip()
        if not asset_id:
            raise QgsProcessingException(tr("Asset ID is required."))
        type_index = self.parameterAsEnum(parameters, self.ASSET_TYPE, context)
        asset_type = None if type_index == 0 else self.TYPES[type_index]
        if not is_ee_initialized() and not initialize_ee():
            raise QgsProcessingException(tr("Earth Engine is not initialized."))
        if asset_type is None:
            asset_type = detect_asset_type(asset_id)
        name = (
            self.parameterAsString(parameters, self.NAME, context).strip()
            or asset_id.split("/")[-1]
        )
        opacity = self.parameterAsDouble(parameters, self.OPACITY, context)
        mosaic = self.parameterAsBoolean(parameters, self.MOSAIC_COLLECTION, context)

        if asset_type == "Image":
            ee_object = ee.Image(asset_id)
        elif asset_type == "ImageCollection":
            collection = ee.ImageCollection(asset_id)
            ee_object = collection.mosaic() if mosaic else collection
        elif asset_type == "FeatureCollection":
            ee_object = ee.FeatureCollection(asset_id)
        else:
            raise QgsProcessingException(tr(f"Unsupported asset type: {asset_type}"))

        add_ee_layer(ee_object, {}, name, opacity=opacity)
        feedback.pushInfo(tr(f"Loaded {name}"))
        return {self.OUTPUT_NAME: name}


class GeeDataCatalogsProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(SearchCatalogAlgorithm())
        self.addAlgorithm(GenerateSnippetAlgorithm())
        self.addAlgorithm(LoadAssetAlgorithm())

    def id(self):
        return "gee_data_catalogs"

    def name(self):
        return tr("GEE Data Catalogs")

    def longName(self):
        return self.name()

    def icon(self):
        from qgis.PyQt.QtGui import QIcon
        import os

        return QIcon(os.path.join(os.path.dirname(__file__), "icons", "icon.svg"))
