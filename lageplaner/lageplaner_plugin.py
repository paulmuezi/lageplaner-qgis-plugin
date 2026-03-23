from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request
import ast
from typing import Any, Callable

from qgis.PyQt.QtCore import QPointF, Qt, QTimer, QSettings
from qgis.PyQt.QtGui import QColor, QFont, QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsMarkerLineSymbolLayer,
    QgsPalLayerSettings,
    QgsProject,
    QgsProperty,
    QgsPropertyCollection,
    QgsRendererCategory,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsTask,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)


PLUGIN_NAME = "Lageplaner"
SETTINGS_PREFIX = "lageplaner_qgis_plugin"
DEFAULT_API_BASE = "https://api.lageplaner.de/v1"
DEFAULT_WIDTH_M = 500.0
DEFAULT_HEIGHT_M = 500.0
MAX_AREA_SQ_KM = 1.0
POLL_INTERVAL_MS = 1500
LAYER_ORDER = ["polygons", "lines", "points", "labels"]
LAYER_LABELS = {
    "polygons": "Flächen",
    "lines": "Linien",
    "points": "Punkte",
    "labels": "Beschriftungen",
}

LAND_USE_THEMES = {
    "Wohnbauflächen",
    "Industrie und Gewerbe",
    "Sport und Freizeit",
    "Vegetation",
    "Verkehr",
    "Gewässer",
    "Rechtliche Festlegungen",
}

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "signatur_catalog.json")
with open(_CATALOG_PATH, "r", encoding="utf-8") as _catalog_handle:
    _SIGNATURE_CATALOG = json.load(_catalog_handle)

GLOBAL_SIGNATURE_LABELS: dict[str, str] = _SIGNATURE_CATALOG.get("global", {})
THEME_SIGNATURE_LABELS: dict[str, dict[str, str]] = _SIGNATURE_CATALOG.get("themes", {})
PLACEHOLDER_SIGNATURE_LABELS = {"[1401]", "[1403]", "[1404]", "[1405]", "[1501]", "[1510]", "[1524]", "[2031]", "[2515]", "[2524]", "[3653]", "[rn1305]", "[rn1501]"}
BUILDING_GENERIC_LABELS = {"Gebäude", "Öffentliches Gebäude"}
LINE_DENSITY_OVERRIDES = {"Politische Grenzen": 0.35, "Rechtliche Festlegungen": 0.35, "Verkehr": 0.5}


def _settings_key(name: str) -> str:
    return f"{SETTINGS_PREFIX}/{name}"


class HttpJsonTask(QgsTask):
    def __init__(
        self,
        *,
        description: str,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any] | None = None,
        on_success: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(description, QgsTask.CanCancel)
        self._method = method
        self._url = url
        self._headers = headers
        self._payload = payload
        self._on_success = on_success
        self._on_error = on_error
        self.result_data: dict[str, Any] | None = None
        self.error_message: str | None = None

    def run(self) -> bool:
        try:
            data = None if self._payload is None else json.dumps(self._payload).encode("utf-8")
            request = urllib.request.Request(
                self._url,
                data=data,
                headers=self._headers,
                method=self._method,
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
            self.result_data = json.loads(body) if body else {}
            return True
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read().decode("utf-8")
            except Exception:
                payload = ""
            self.error_message = f"HTTP {exc.code}: {payload or exc.reason}"
            return False
        except Exception as exc:
            self.error_message = str(exc)
            return False

    def finished(self, result: bool) -> None:
        if result and self.result_data is not None:
            if self._on_success:
                self._on_success(self.result_data)
            return

        if self._on_error:
            self._on_error(self.error_message or "Unbekannter API-Fehler")


class HttpDownloadTask(QgsTask):
    def __init__(
        self,
        *,
        description: str,
        url: str,
        output_path: str,
        on_success: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(description, QgsTask.CanCancel)
        self._url = url
        self._output_path = output_path
        self._on_success = on_success
        self._on_error = on_error
        self.error_message: str | None = None

    def run(self) -> bool:
        try:
            with urllib.request.urlopen(self._url, timeout=120) as response:
                payload = response.read()
            with open(self._output_path, "wb") as handle:
                handle.write(payload)
            return True
        except urllib.error.HTTPError as exc:
            self.error_message = f"HTTP {exc.code}: {exc.reason}"
            return False
        except Exception as exc:
            self.error_message = str(exc)
            return False

    def finished(self, result: bool) -> None:
        if result:
            if self._on_success:
                self._on_success(self._output_path)
            return

        if self._on_error:
            self._on_error(self.error_message or "Download fehlgeschlagen")


class LageplanerDialog(QDialog):
    def __init__(self, plugin: "LageplanerPlugin") -> None:
        super().__init__(plugin.iface.mainWindow())
        self.plugin = plugin
        self.iface = plugin.iface
        self.current_task_id: str | None = None
        self.current_output_path: str | None = None
        self.setWindowTitle("Lageplaner")
        self.setMinimumWidth(520)
        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        logo_label = QLabel()
        logo_label.setPixmap(QIcon(self.plugin.icon_path).pixmap(48, 48))
        title_wrap = QVBoxLayout()
        title = QLabel("Lageplaner")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        helper = QLabel(
            "Datenstand und Lizenzen je Bundesland: lageplaner.de/quelldaten\n"
            "Aktuell ohne Bayern und Sachsen-Anhalt."
        )
        helper.setStyleSheet("color: #94a3b8; font-size: 12px;")
        helper.setWordWrap(True)
        title_wrap.addWidget(title)
        title_wrap.addWidget(helper)
        header.addWidget(logo_label)
        header.addLayout(title_wrap)
        header.addStretch(1)
        layout.addLayout(header)

        connection_group = QGroupBox("API")
        connection_form = QFormLayout(connection_group)
        self.api_base_label = QLabel(DEFAULT_API_BASE)
        self.api_base_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.api_base_label.setStyleSheet("color: #94a3b8;")
        connection_form.addRow("API Endpoint", self.api_base_label)
        layout.addWidget(connection_group)

        area_group = QGroupBox("Ausschnitt")
        area_grid = QGridLayout(area_group)
        self.center_lat_input = QLineEdit()
        self.center_lon_input = QLineEdit()
        self.width_input = QDoubleSpinBox()
        self.width_input.setRange(1, 10000)
        self.width_input.setDecimals(0)
        self.width_input.setSuffix(" m")
        self.height_input = QDoubleSpinBox()
        self.height_input.setRange(1, 10000)
        self.height_input.setDecimals(0)
        self.height_input.setSuffix(" m")
        self.use_extent_button = QPushButton("Aus Kartenfenster übernehmen")
        self.use_extent_button.clicked.connect(self.fill_from_canvas_extent)
        area_grid.addWidget(QLabel("Lat"), 0, 0)
        area_grid.addWidget(self.center_lat_input, 0, 1)
        area_grid.addWidget(QLabel("Lon"), 0, 2)
        area_grid.addWidget(self.center_lon_input, 0, 3)
        area_grid.addWidget(QLabel("Breite"), 1, 0)
        area_grid.addWidget(self.width_input, 1, 1)
        area_grid.addWidget(QLabel("Höhe"), 1, 2)
        area_grid.addWidget(self.height_input, 1, 3)
        area_grid.addWidget(self.use_extent_button, 2, 0, 1, 4)
        self.area_limit_label = QLabel("")
        self.area_limit_label.setWordWrap(True)
        self.area_limit_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
        self.area_limit_label.hide()
        area_grid.addWidget(self.area_limit_label, 3, 0, 1, 4)
        self.width_input.valueChanged.connect(self._update_area_limit_state)
        self.height_input.valueChanged.connect(self._update_area_limit_state)
        layout.addWidget(area_group)

        output_group = QGroupBox("Ausgabe")
        output_row = QHBoxLayout(output_group)
        self.output_path_input = QLineEdit()
        self.output_path_input.setPlaceholderText("Optional: Zielpfad für das GeoPackage")
        browse_button = QPushButton("Speichern unter...")
        browse_button.clicked.connect(self.choose_output_path)
        output_row.addWidget(self.output_path_input, 1)
        output_row.addWidget(browse_button)
        layout.addWidget(output_group)

        self.status_label = QLabel("Bereit")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #ffffff; padding: 2px 0;")
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.start_button = QPushButton("Layer laden")
        self.start_button.clicked.connect(self.start_extract)
        self.close_button = QPushButton("Schließen")
        self.close_button.clicked.connect(self.close)
        actions.addWidget(self.close_button)
        actions.addWidget(self.start_button)
        layout.addLayout(actions)

    def _current_area_sq_km(self) -> float:
        return (self.width_input.value() * self.height_input.value()) / 1_000_000

    def _update_area_limit_state(self) -> None:
        area_sq_km = self._current_area_sq_km()
        over_limit = area_sq_km > MAX_AREA_SQ_KM
        self.start_button.setEnabled(not over_limit)
        if over_limit:
            self.area_limit_label.setText(
                f"Der aktuelle Ausschnitt ist {area_sq_km:.2f} km² groß. "
                f"Maximal erlaubt sind {MAX_AREA_SQ_KM:g} km² pro Export."
            )
            self.area_limit_label.show()
        else:
            self.area_limit_label.hide()

    def _load_settings(self) -> None:
        settings = QSettings()
        self.width_input.setValue(float(settings.value(_settings_key("width_m"), DEFAULT_WIDTH_M)))
        self.height_input.setValue(float(settings.value(_settings_key("height_m"), DEFAULT_HEIGHT_M)))
        self.output_path_input.setText(settings.value(_settings_key("output_path"), ""))
        self._update_area_limit_state()

    def _save_settings(self) -> None:
        settings = QSettings()
        settings.setValue(_settings_key("width_m"), self.width_input.value())
        settings.setValue(_settings_key("height_m"), self.height_input.value())
        settings.setValue(_settings_key("output_path"), self.output_path_input.text().strip())

    def choose_output_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "GeoPackage speichern",
            self.output_path_input.text().strip() or "lageplaner_extract.gpkg",
            "GeoPackage (*.gpkg)",
        )
        if path:
            if not path.lower().endswith(".gpkg"):
                path += ".gpkg"
            self.output_path_input.setText(path)

    def fill_from_canvas_extent(self) -> None:
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        source_crs = canvas.mapSettings().destinationCrs()
        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        center = transform.transform(extent.center())
        self.center_lat_input.setText(f"{center.y():.8f}")
        self.center_lon_input.setText(f"{center.x():.8f}")

        metric_crs = QgsCoordinateReferenceSystem("EPSG:25832" if center.x() <= 12 else "EPSG:25833")
        metric_transform = QgsCoordinateTransform(source_crs, metric_crs, QgsProject.instance())
        bottom_left = metric_transform.transform(extent.xMinimum(), extent.yMinimum())
        top_right = metric_transform.transform(extent.xMaximum(), extent.yMaximum())
        self.width_input.setValue(max(1.0, abs(top_right.x() - bottom_left.x())))
        self.height_input.setValue(max(1.0, abs(top_right.y() - bottom_left.y())))
        self._update_area_limit_state()
        self.status_label.setText("Kartenausschnitt übernommen.")

    def _api_headers(self, *, include_json: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
        }
        if include_json:
            headers["Content-Type"] = "application/json"
        return headers

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.start_button.setDisabled(busy or self._current_area_sq_km() > MAX_AREA_SQ_KM)
        self.use_extent_button.setDisabled(busy)
        if message:
            self.status_label.setText(message)

    def _show_error(self, message: str) -> None:
        self._set_busy(False, message)
        self.iface.messageBar().pushMessage(PLUGIN_NAME, message, level=Qgis.Critical, duration=8)

    def _show_info(self, message: str) -> None:
        self.status_label.setText(message)
        self.iface.messageBar().pushMessage(PLUGIN_NAME, message, level=Qgis.Info, duration=5)

    def _process_ui(self) -> None:
        QApplication.processEvents()

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers=self._api_headers(include_json=payload is not None),
            method=method,
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    def _download_file(self, *, url: str, output_path: str) -> None:
        with urllib.request.urlopen(url, timeout=180) as response:
            payload = response.read()
        with open(output_path, "wb") as handle:
            handle.write(payload)

    def start_extract(self) -> None:
        api_base = DEFAULT_API_BASE

        try:
            lat = float(self.center_lat_input.text().strip())
            lon = float(self.center_lon_input.text().strip())
        except ValueError:
            self._show_error("Lat und Lon müssen gültige Zahlen sein.")
            return

        self._save_settings()
        self.current_task_id = None
        self.current_output_path = self._resolve_output_path()
        area_sq_km = self._current_area_sq_km()
        if area_sq_km > MAX_AREA_SQ_KM:
            self._show_error(
                f"Der Export ist auf maximal {MAX_AREA_SQ_KM:g} km² begrenzt "
                f"(aktuell {area_sq_km:.2f} km²)."
            )
            return
        payload = {
            "center": {"lat": lat, "lon": lon},
            "width_m": self.width_input.value(),
            "height_m": self.height_input.value(),
        }
        self._set_busy(True, "GeoPackage-Job wird gestartet...")
        self._process_ui()
        try:
            start_payload = self._request_json(
                method="POST",
                url=f"{api_base}/geopackage",
                payload=payload,
            )
            task_id = str(start_payload.get("task_id") or "")
            if not task_id:
                raise RuntimeError("Die API hat keine task_id zurückgegeben.")

            self.current_task_id = task_id
            self.status_label.setText(f"GeoPackage-Job gestartet ({task_id[:8]}...).")
            self._process_ui()

            final_payload = None
            for _ in range(60):
                status_payload = self._request_json(
                    method="GET",
                    url=f"{api_base}/geopackage/{task_id}",
                )
                finished = bool(status_payload.get("finished"))
                message = str(status_payload.get("message") or "")
                self.status_label.setText(message or f"Status wird abgefragt ({task_id[:8]}...)")
                self._process_ui()
                if finished:
                    final_payload = status_payload
                    break
                time.sleep(POLL_INTERVAL_MS / 1000)

            if final_payload is None:
                raise RuntimeError("Der GeoPackage-Job hat nicht rechtzeitig geantwortet.")

            outputs = final_payload.get("outputs", []) or []
            message = str(final_payload.get("message") or "")
            error_code = str(final_payload.get("error_code") or "").strip()
            if message != "Completed":
                if error_code:
                    raise RuntimeError(f"[{error_code}] {message or 'GeoPackage-Job fehlgeschlagen.'}")
                raise RuntimeError(message or "GeoPackage-Job fehlgeschlagen.")
            if not outputs:
                raise RuntimeError("Der Job ist fertig, aber es wurde kein GeoPackage zurückgegeben.")

            output = outputs[0]
            url = str(output.get("url") or "")
            if not url:
                raise RuntimeError("Der Download-Link fehlt.")

            filename = str(output.get("filename") or "lageplaner_extract.gpkg")
            self.status_label.setText(f"GeoPackage wird heruntergeladen ({filename})...")
            self._process_ui()
            self._download_file(url=url, output_path=self.current_output_path or self._resolve_output_path())
            self._handle_download_success(self.current_output_path or self._resolve_output_path())
        except Exception as exc:
            self._show_error(str(exc))

    def _resolve_output_path(self) -> str:
        configured = self.output_path_input.text().strip()
        if configured:
            return configured
        return os.path.join(tempfile.gettempdir(), "lageplaner_extract.gpkg")

    def _handle_download_success(self, path: str) -> None:
        try:
            self._load_geopackage_layers(path)
            self._set_busy(False, f"GeoPackage geladen: {path}")
            self.iface.messageBar().pushMessage(
                PLUGIN_NAME,
                f"GeoPackage erfolgreich geladen: {os.path.basename(path)}",
                level=Qgis.Success,
                duration=6,
            )
        except Exception as exc:
            self._show_error(f"GeoPackage konnte nicht in QGIS geladen werden: {exc}")

    def _load_geopackage_layers(self, path: str) -> None:
        connection = sqlite3.connect(path)
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT table_name FROM gpkg_contents ORDER BY table_name")
            layer_names = [row[0] for row in cursor.fetchall()]
        finally:
            connection.close()

        group = QgsProject.instance().layerTreeRoot().insertGroup(0, "Lageplaner")
        ordered_names = sorted(
            layer_names,
            key=lambda name: (LAYER_ORDER.index(name) if name in LAYER_ORDER else len(LAYER_ORDER), name),
        )
        loaded = 0
        style_warnings: list[str] = []
        for layer_name in ordered_names:
            display_name = LAYER_LABELS.get(layer_name, layer_name)
            layer = QgsVectorLayer(f"{path}|layername={layer_name}", display_name, "ogr")
            if not layer.isValid():
                continue
            QgsProject.instance().addMapLayer(layer, False)
            group.insertLayer(0, layer)
            try:
                self._apply_layer_style(layer, layer_name)
            except Exception as exc:
                style_warnings.append(f"{display_name}: {exc}")
            loaded += 1

        if loaded == 0:
            raise RuntimeError("Keine gültigen Layer im GeoPackage gefunden.")

        if style_warnings:
            self.iface.messageBar().pushMessage(
                PLUGIN_NAME,
                "Layer wurden geladen, aber einzelne Styles konnten nicht vollständig angewendet werden: "
                + "; ".join(style_warnings[:3]),
                level=Qgis.Warning,
                duration=12,
            )

        try:
            self.iface.mapCanvas().refreshAllLayers()
        except Exception:
            self.iface.mapCanvas().refresh()

    def _apply_layer_style(self, layer: QgsVectorLayer, layer_name: str) -> None:
        if layer_name == "polygons":
            self._apply_safe_polygon_style(layer)
        elif layer_name == "lines":
            self._apply_safe_line_style(layer)
        elif layer_name == "points":
            self._apply_safe_point_style(layer)
        elif layer_name == "labels":
            self._apply_safe_label_style(layer)
        self._apply_render_order(layer, layer_name)
        layer.triggerRepaint()

    def _apply_safe_polygon_style(self, layer: QgsVectorLayer) -> None:
        fields = self._field_names(layer)
        if "fill_color" not in fields:
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": "#e9e3d7",
                    "outline_color": "#697384",
                    "outline_width": "0.16",
                }
            )
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            return

        semantic_fields = ["signaturnummer", "thema", "sub_thema"]
        available_semantic_fields = [field for field in semantic_fields if field in fields]
        if not available_semantic_fields:
            available_semantic_fields = ["fill_color"]

        feature_map: dict[tuple[str, ...], Any] = {}
        for feature in layer.getFeatures():
            if str(feature["thema"] or "").strip() == "Rechtliche Festlegungen":
                continue
            fill = str(feature["fill_color"] or "").strip()
            if not fill:
                continue
            key = tuple(
                "" if feature[field] is None else str(feature[field]).strip()
                for field in available_semantic_fields
            )
            if key in feature_map:
                continue
            feature_map[key] = feature
            if len(feature_map) >= 80:
                break

        if not feature_map:
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": "255,255,255,0",
                    "outline_color": "255,255,255,0",
                    "outline_width": "0",
                }
            )
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            return

        label_map = self._build_unique_legend_labels(feature_map)
        categories: list[QgsRendererCategory] = []
        expression = " || '|' || ".join(
            f"coalesce(to_string(\"{field}\"), '')" for field in available_semantic_fields
        )
        for value, label in sorted(label_map.items(), key=lambda item: item[1]):
            feature = feature_map[value]
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": self._normalize_color(str(feature["fill_color"] or "").strip(), fallback="#e9e3d7"),
                    "outline_color": "255,255,255,0",
                    "outline_width": "0",
                }
            )
            try:
                symbol.symbolLayer(0).setStrokeStyle(Qt.PenStyle.NoPen)
            except AttributeError:
                pass
            categories.append(QgsRendererCategory("|".join(value), symbol, label))
        renderer = QgsCategorizedSymbolRenderer(expression, categories)
        try:
            transparent = QgsFillSymbol.createSimple(
                {
                    "color": "255,255,255,0",
                    "outline_color": "255,255,255,0",
                    "outline_width": "0",
                }
            )
            renderer.setSourceSymbol(transparent)
        except Exception:
            pass
        layer.setRenderer(renderer)

    def _apply_safe_line_style(self, layer: QgsVectorLayer) -> None:
        fields = self._field_names(layer)
        style_fields = {"stroke_color", "width_100mm", "pattern_length", "pattern_offset", "pattern_array", "line_cap"}
        if not style_fields.issubset(fields):
            symbol = QgsLineSymbol.createSimple(
                {
                    "line_color": "#4d5b73",
                    "line_width": "0.30",
                }
            )
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            return

        semantic_fields = ["signaturnummer", "thema", "sub_thema", "line_cap"]
        available_semantic_fields = [field for field in semantic_fields if field in fields]
        if not available_semantic_fields:
            available_semantic_fields = ["stroke_color", "width_100mm", "pattern_length", "pattern_offset", "pattern_array", "line_cap"]

        feature_map: dict[tuple[str, ...], Any] = {}
        for feature in layer.getFeatures():
            combo = tuple(
                "" if feature[field] is None else str(feature[field]).strip()
                for field in available_semantic_fields
            )
            if combo in feature_map:
                continue
            feature_map[combo] = feature
            if len(feature_map) >= 120:
                break

        if not feature_map:
            symbol = QgsLineSymbol.createSimple(
                {
                    "line_color": "#4d5b73",
                    "line_width": "0.30",
                }
            )
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            return

        label_map = self._build_unique_legend_labels(feature_map)
        categories: list[QgsRendererCategory] = []
        expression = " || '|' || ".join(
            f"coalesce(to_string(\"{field}\"), '')" for field in available_semantic_fields
        )
        for combo, label in sorted(label_map.items(), key=lambda item: item[1]):
            feature = feature_map[combo]
            symbol = self._build_line_symbol_from_style(
                str(feature["stroke_color"] or "").strip(),
                feature["width_100mm"],
                feature["pattern_length"],
                feature["pattern_offset"],
                str(feature["pattern_array"] or "").strip(),
                str(feature["line_cap"] or "").strip(),
                str(feature["thema"] or "").strip(),
                feature["layer_index"],
            )
            key = "|".join(combo)
            categories.append(QgsRendererCategory(key, symbol, label))
        renderer = QgsCategorizedSymbolRenderer(expression, categories)
        layer.setRenderer(renderer)

    def _apply_safe_point_style(self, layer: QgsVectorLayer) -> None:
        fields = self._field_names(layer)
        svg_renderer = self._build_safe_svg_point_renderer(layer, fields)
        if svg_renderer is not None:
            layer.setRenderer(svg_renderer)
            return

        symbol = QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "color": "#1f2937",
                "outline_color": "#ffffff",
                "outline_width": "0.2",
                "size": "2.0",
            }
        )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

    def _apply_render_order(self, layer: QgsVectorLayer, layer_name: str) -> None:
        renderer = layer.renderer()
        if renderer is None:
            return

        fields = self._field_names(layer)
        clauses: list[tuple[str, bool]] = []
        if layer_name == "polygons":
            if "theme_index" in fields:
                clauses.append(("\"theme_index\"", False))
            if "z_index" in fields:
                clauses.append(("\"z_index\"", True))
        elif layer_name == "lines":
            if "theme_index" in fields:
                clauses.append(("\"theme_index\"", False))
            if "z_order" in fields:
                clauses.append(("\"z_order\"", True))
            else:
                if "layer_index" in fields:
                    clauses.append(("\"layer_index\"", True))
                if "z_index_base" in fields:
                    clauses.append(("\"z_index_base\"", True))
        elif layer_name in {"points", "labels"} and "theme_index" in fields:
            clauses.append(("\"theme_index\"", False))

        if not clauses:
            return

        try:
            order = QgsFeatureRequest.OrderBy(
                [QgsFeatureRequest.OrderByClause(expression, ascending) for expression, ascending in clauses]
            )
            renderer.setOrderBy(order)
            renderer.setOrderByEnabled(True)
        except Exception:
            return

    def _apply_safe_label_style(self, layer: QgsVectorLayer) -> None:
        fields = self._field_names(layer)
        label_field = "text_content" if "text_content" in fields else ("text" if "text" in fields else None)
        if not label_field:
            layer.setLabelsEnabled(False)
            return

        semantic_fields = ["signaturnummer", "thema", "sub_thema"]
        available_semantic_fields = [field for field in semantic_fields if field in fields]
        if available_semantic_fields:
            feature_map: dict[tuple[str, ...], Any] = {}
            for feature in layer.getFeatures():
                key = tuple(
                    "" if feature[field] is None else str(feature[field]).strip()
                    for field in available_semantic_fields
                )
                if key in feature_map:
                    continue
                feature_map[key] = feature
                if len(feature_map) >= 40:
                    break

            categories: list[QgsRendererCategory] = []
            expression = " || '|' || ".join(
                f"coalesce(to_string(\"{field}\"), '')" for field in available_semantic_fields
            )
            label_map = self._build_unique_label_group_names(feature_map)
            for key, feature in sorted(feature_map.items(), key=lambda item: label_map[item[0]]):
                symbol = QgsMarkerSymbol()
                symbol.setSize(0.0)
                categories.append(QgsRendererCategory("|".join(key), symbol, label_map[key]))
            if categories:
                layer.setRenderer(QgsCategorizedSymbolRenderer(expression, categories))
            else:
                hidden_symbol = QgsMarkerSymbol()
                hidden_symbol.setSize(0.0)
                layer.setRenderer(QgsSingleSymbolRenderer(hidden_symbol))
        else:
            # Hide the source marker itself and let PAL render only the text.
            hidden_symbol = QgsMarkerSymbol()
            hidden_symbol.setSize(0.0)
            layer.setRenderer(QgsSingleSymbolRenderer(hidden_symbol))

        pal = QgsPalLayerSettings()
        pal.enabled = True
        pal.fieldName = label_field
        # norBIT also keeps point labels in AroundPoint mode and anchors them
        # via explicit X/Y positions.
        pal.placement = QgsPalLayerSettings.AroundPoint
        pal.dist = 0
        pal.upsidedownLabels = QgsPalLayerSettings.ShowAll

        text_format = QgsTextFormat()
        font = QFont("Arial")
        font.setPointSizeF(2.5)
        text_format.setFont(font)
        text_format.setSize(1.2)
        text_format.setSizeUnit(QgsUnitTypes.RenderMapUnits)
        text_format.setColor(QColor("#111111"))

        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setColor(QColor("#ffffff"))
        buffer_settings.setSize(0.2)
        buffer_settings.setSizeUnit(QgsUnitTypes.RenderMapUnits)
        text_format.setBuffer(buffer_settings)
        pal.setFormat(text_format)

        data_defined = QgsPropertyCollection()
        if "raw_grad_pt" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.Size,
                QgsProperty.fromExpression(
                    "case "
                    "when coalesce(\"raw_grad_pt\", 0) < 0 then abs(\"raw_grad_pt\") "
                    "else 0.25 * coalesce(\"raw_skalierung\", 1) * coalesce(\"raw_grad_pt\", 0) "
                    "end"
                ),
            )
        if "font_family" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.Family,
                QgsProperty.fromField("font_family"),
            )
        if "is_italic" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.Italic,
                QgsProperty.fromField("is_italic"),
            )
        if "is_bold" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.Bold,
                QgsProperty.fromField("is_bold"),
            )
        if "raw_halign" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.Hali,
                QgsProperty.fromExpression(
                    "case "
                    "when \"raw_halign\" in ('linksbündig', 'Left') then 'Left' "
                    "when \"raw_halign\" in ('rechtsbündig', 'Right') then 'Right' "
                    "when \"raw_halign\" in ('zentriert', 'zentrisch', 'Center') then 'Center' "
                    "else 'Center' end"
                ),
            )
        if "raw_valign" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.Vali,
                QgsProperty.fromExpression(
                    "case "
                    "when \"raw_valign\" in ('oben', 'Top') then 'Top' "
                    "when \"raw_valign\" in ('unten', 'Bottom') then 'Bottom' "
                    "when \"raw_valign\" in ('Mitte', 'Center') then 'Half' "
                    "when \"raw_valign\" in ('Basis', 'Base', 'Baseline') then 'Base' "
                    "else 'Base' end"
                ),
            )
        if "font_color" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.Color,
                QgsProperty.fromField("font_color"),
            )
        if "raw_rotation" in fields:
            data_defined.setProperty(
                QgsPalLayerSettings.LabelRotation,
                QgsProperty.fromExpression("-coalesce(\"raw_rotation\", 0)"),
            )
        data_defined.setProperty(
            QgsPalLayerSettings.PositionX,
            QgsProperty.fromExpression("x($geometry)"),
        )
        data_defined.setProperty(
            QgsPalLayerSettings.PositionY,
            QgsProperty.fromExpression("y($geometry)"),
        )
        data_defined.setProperty(
            QgsPalLayerSettings.AlwaysShow,
            QgsProperty.fromExpression("true"),
        )
        pal.setDataDefinedProperties(data_defined)

        layer.setLabelsEnabled(True)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.triggerRepaint()

    def _build_safe_svg_point_renderer(
        self,
        layer: QgsVectorLayer,
        fields: set[str],
    ) -> QgsCategorizedSymbolRenderer | None:
        if "svg_filename" not in fields:
            return None

        symbol_map: dict[str, tuple[float, float, float]] = {}
        feature_map: dict[str, Any] = {}
        for feature in layer.getFeatures():
            filename = str(feature["svg_filename"] or "").strip()
            if not filename or filename in symbol_map:
                continue
            svg_path = self._resolve_svg_path(filename)
            if svg_path is None:
                continue
            size_m, offset_x, offset_y = self._point_symbol_geometry(feature)
            symbol_map[filename] = (size_m, offset_x, offset_y)
            feature_map[filename] = feature
            if len(symbol_map) >= 200:
                break

        if not symbol_map:
            return None

        label_map = self._build_unique_legend_labels(feature_map)
        categories: list[QgsRendererCategory] = []
        for filename, (size_m, offset_x, offset_y) in sorted(symbol_map.items(), key=lambda item: label_map.get(item[0], item[0])):
            svg_path = self._resolve_svg_path(filename)
            if svg_path is None:
                continue
            symbol = QgsMarkerSymbol()
            svg_layer = QgsSvgMarkerSymbolLayer(svg_path)
            svg_layer.setOutputUnit(QgsUnitTypes.RenderMapUnits)
            svg_layer.setSize(size_m)
            svg_layer.setOffset(QPointF(offset_x, offset_y))
            symbol.changeSymbolLayer(0, svg_layer)
            symbol.setOutputUnit(QgsUnitTypes.RenderMapUnits)
            symbol.setSize(size_m)
            categories.append(QgsRendererCategory(filename, symbol, label_map.get(filename, filename)))

        if not categories:
            return None

        return QgsCategorizedSymbolRenderer("svg_filename", categories)

    def _field_names(self, layer: QgsVectorLayer) -> set[str]:
        return {field.name() for field in layer.fields()}

    def _distinct_field_values(self, layer: QgsVectorLayer, field_name: str, *, limit: int) -> list[str]:
        values: set[str] = set()
        for feature in layer.getFeatures():
            raw_value = feature[field_name]
            value = str(raw_value or "").strip()
            if not value:
                continue
            values.add(value)
            if len(values) >= limit:
                break
        return sorted(values)

    def _usage_label_from_feature(self, feature) -> str:
        thema = str(feature["thema"] or "").strip()
        sub_thema = str(feature["sub_thema"] or "").strip()
        signatur = str(feature["signaturnummer"] or "").strip()
        catalog_label = self._preferred_catalog_label(signatur, thema=thema, sub_thema=sub_thema)
        if catalog_label:
            return catalog_label
        if thema in LAND_USE_THEMES:
            return thema
        if sub_thema and sub_thema not in {"None", "Flächen", "Gebäude"} and not sub_thema.startswith("None"):
            if thema and sub_thema.lower() != thema.lower():
                return f"{thema} / {sub_thema}"
            return sub_thema
        if thema:
            return thema
        return signatur or "ALKIS"

    def _format_signatur_label(self, signatur: str, label: str) -> str:
        clean_signatur = self._display_signatur(signatur)
        clean_label = str(label or "").strip()
        if clean_signatur and clean_label:
            return f"{clean_signatur} - {clean_label}"
        return clean_signatur or clean_label or "ALKIS"

    def _display_signatur(self, signatur: str) -> str:
        raw = str(signatur or "").strip()
        parts = self._signatur_parts(raw)
        if len(parts) > 1 and all(part and not part.startswith("rn") for part in parts):
            return " ".join(parts)
        return raw

    def _legend_base_label_from_feature(self, feature) -> str:
        signatur = str(feature["signaturnummer"] or "").strip()
        return self._format_signatur_label(signatur, self._usage_label_from_feature(feature))

    def _label_base_label_from_feature(self, feature) -> str:
        signatur = str(feature["signaturnummer"] or "").strip()
        return self._format_signatur_label(signatur, self._label_group_name(feature))

    def _label_group_name(self, feature) -> str:
        thema = str(feature["thema"] or "").strip()
        sub_thema = str(feature["sub_thema"] or "").strip()
        signatur = str(feature["signaturnummer"] or "").strip()
        if thema == "Flurstücke" and sub_thema == "Nummern":
            return "Flurstücksnummern"
        if thema == "Gebäude" and sub_thema == "Funktion":
            return "Gebäudefunktionen"
        if thema == "Gebäude":
            return "Hausnummern"
        if thema == "Lagebezeichnungen":
            return "Lagebezeichnungen"
        if sub_thema and sub_thema not in {"None", "Gebäude"}:
            return f"{thema} / {sub_thema}" if thema else sub_thema
        if thema:
            return thema
        return signatur or "Beschriftungen"

    def _label_group_detail(self, feature) -> str:
        thema = str(feature["thema"] or "").strip()
        sub_thema = str(feature["sub_thema"] or "").strip()
        signatur = str(feature["signaturnummer"] or "").strip()

        secondary = self._secondary_catalog_label(signatur, thema=thema, sub_thema=sub_thema)
        if secondary:
            return secondary

        primary = self._preferred_catalog_label(signatur, thema=thema, sub_thema=sub_thema)
        if primary and primary != self._label_group_name(feature):
            return primary

        if sub_thema and sub_thema not in {"None", "Nummern", "Gebäude"} and not sub_thema.startswith("None"):
            return sub_thema

        return signatur or ""

    def _build_unique_label_group_names(self, feature_map: dict[Any, Any]) -> dict[Any, str]:
        labels: dict[Any, tuple[str, str]] = {}
        counts: dict[str, int] = {}
        for key, feature in feature_map.items():
            base = self._label_base_label_from_feature(feature)
            detail = self._label_group_detail(feature)
            labels[key] = (base, detail)
            counts[base] = counts.get(base, 0) + 1

        deduped: dict[Any, str] = {}
        sequence: dict[str, int] = {}
        for key, (base, detail) in labels.items():
            if counts.get(base, 0) <= 1:
                deduped[key] = base
                continue

            if detail and detail.lower() != base.lower() and detail.lower() not in base.lower():
                deduped[key] = f"{base} · {detail}"
                continue

            current = sequence.get(base, 0) + 1
            sequence[base] = current
            deduped[key] = f"{base} ({current})"

        return deduped

    def _legend_detail_from_feature(self, feature) -> str:
        field_names = {field.name() for field in feature.fields()}
        sub_thema = str(feature["sub_thema"] or "").strip() if "sub_thema" in field_names else ""
        thema = str(feature["thema"] or "").strip() if "thema" in field_names else ""
        line_cap = str(feature["line_cap"] or "").strip() if "line_cap" in field_names else ""
        signatur = str(feature["signaturnummer"] or "").strip() if "signaturnummer" in field_names else ""
        if line_cap == "Pfeil":
            return "Pfeil"
        if line_cap == "Abgeschnitten" and ("Nummern" in sub_thema or "Nummern" in thema):
            return "Strich"
        secondary_catalog = self._secondary_catalog_label(signatur, thema=thema, sub_thema=sub_thema)
        if secondary_catalog:
            return secondary_catalog
        if sub_thema and sub_thema not in {"None", "Flächen"} and not sub_thema.startswith("None"):
            return sub_thema
        return ""

    def _catalog_label_for_signatur(self, signatur: str, *, thema: str = "") -> str | None:
        if not signatur:
            return None

        theme_labels = THEME_SIGNATURE_LABELS.get(thema, {})
        direct = self._normalize_catalog_label(theme_labels.get(signatur))
        if direct:
            return direct

        return self._normalize_catalog_label(GLOBAL_SIGNATURE_LABELS.get(signatur))

    def _normalize_catalog_label(self, label: str | None) -> str | None:
        value = str(label or "").strip()
        if not value or value in PLACEHOLDER_SIGNATURE_LABELS:
            return None
        return value

    def _signatur_parts(self, signatur: str) -> list[str]:
        if not signatur:
            return []
        if signatur.startswith("rn"):
            return [signatur]
        if signatur.isdigit() and len(signatur) > 4 and len(signatur) % 4 == 0:
            return [signatur[idx : idx + 4] for idx in range(0, len(signatur), 4)]
        return [signatur]

    def _catalog_labels_for_signatur(self, signatur: str, *, thema: str = "") -> list[str]:
        labels: list[str] = []
        for part in reversed(self._signatur_parts(signatur)):
            label = self._catalog_label_for_signatur(part, thema=thema)
            if label and label not in labels:
                labels.append(label)
        exact = self._catalog_label_for_signatur(signatur, thema=thema)
        if exact and exact not in labels:
            labels.insert(0, exact)
        return labels

    def _preferred_catalog_label(self, signatur: str, *, thema: str = "", sub_thema: str = "") -> str | None:
        labels = self._catalog_labels_for_signatur(signatur, thema=thema)
        if not labels:
            return None

        if thema == "Gebäude":
            for label in labels:
                if label not in BUILDING_GENERIC_LABELS:
                    return label
            return labels[0]

        for label in labels:
            if label != thema:
                return label

        if thema in LAND_USE_THEMES:
            return thema

        return labels[0]

    def _secondary_catalog_label(self, signatur: str, *, thema: str = "", sub_thema: str = "") -> str | None:
        primary = self._preferred_catalog_label(signatur, thema=thema, sub_thema=sub_thema)
        if not primary:
            return None

        for label in self._catalog_labels_for_signatur(signatur, thema=thema):
            if label == primary:
                continue
            if thema == "Gebäude" and label in BUILDING_GENERIC_LABELS:
                continue
            if label == thema:
                continue
            return label
        return None

    def _build_unique_legend_labels(self, feature_map: dict[Any, Any]) -> dict[Any, str]:
        labels: dict[Any, tuple[str, str]] = {}
        counts: dict[str, int] = {}
        for key, feature in feature_map.items():
            base = self._legend_base_label_from_feature(feature)
            detail = self._legend_detail_from_feature(feature)
            labels[key] = (base, detail)
            counts[base] = counts.get(base, 0) + 1

        deduped: dict[Any, str] = {}
        sequence: dict[str, int] = {}
        for key, (base, detail) in labels.items():
            if counts.get(base, 0) <= 1:
                deduped[key] = base
                continue

            if detail and detail.lower() != base.lower() and detail.lower() not in base.lower():
                deduped[key] = f"{base} · {detail}"
                continue

            current = sequence.get(base, 0) + 1
            sequence[base] = current
            deduped[key] = f"{base} ({current})"

        return deduped

    def _point_symbol_geometry(self, feature) -> tuple[float, float, float]:
        try:
            x0 = float(feature["x0"])
            y0 = float(feature["y0"])
            x1 = float(feature["x1"])
            y1 = float(feature["y1"])
            width = abs(x1 - x0)
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            size_m = max(width, 0.5)
            return size_m, -cx, -cy
        except Exception:
            return 4.0, 0.0, 0.0

    def _distinct_line_styles(
        self,
        layer: QgsVectorLayer,
        *,
        limit: int,
    ) -> list[tuple[str, Any, Any, Any, str, str]]:
        combos: set[tuple[str, Any, Any, Any, str, str]] = set()
        for feature in layer.getFeatures():
            combo = (
                str(feature["stroke_color"] or "").strip(),
                feature["width_100mm"],
                feature["pattern_length"],
                feature["pattern_offset"],
                str(feature["pattern_array"] or "").strip(),
                str(feature["line_cap"] or "").strip(),
            )
            combos.add(combo)
            if len(combos) >= limit:
                break
        return sorted(combos)

    def _normalize_color(self, value: str | None, *, fallback: str) -> str:
        color = str(value or "").strip()
        if not color or color.lower() == "none":
            return fallback
        return color

    def _parse_pattern_array(self, value: str | None) -> list[float]:
        raw = str(value or "").strip()
        if not raw or raw == "<NA>":
            return []
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            return []
        if isinstance(parsed, (int, float)):
            return [float(parsed)]
        if isinstance(parsed, (list, tuple)):
            result = []
            for item in parsed:
                try:
                    result.append(float(item))
                except Exception:
                    continue
            return result
        return []

    def _line_style_key(
        self,
        stroke_color: str,
        width_100mm: Any,
        pattern_length: Any,
        pattern_offset: Any,
        pattern_array: str,
        line_cap: str,
    ) -> str:
        return "|".join(
            [
                str(stroke_color or ""),
                str(width_100mm or ""),
                str(pattern_length or ""),
                str(pattern_offset or ""),
                str(pattern_array or ""),
                str(line_cap or ""),
            ]
        )

    def _build_line_symbol_from_style(
        self,
        stroke_color: str,
        width_100mm: Any,
        pattern_length: Any,
        pattern_offset: Any,
        pattern_array: str,
        line_cap: str,
        thema: str,
        layer_index: Any,
    ) -> QgsLineSymbol:
        width = 0.13
        try:
            if width_100mm is not None:
                width = float(width_100mm) / 100.0
                if width <= 0:
                    width = 0.13
        except Exception:
            width = 0.13
        width *= 0.75

        try:
            pat_len = float(pattern_length) if pattern_length is not None else 0.0
        except Exception:
            pat_len = 0.0
        pat_arr = self._parse_pattern_array(pattern_array)
        density = LINE_DENSITY_OVERRIDES.get(thema, 1.0)
        color = QColor(self._normalize_color(stroke_color, fallback="#000000"))
        try:
            if int(layer_index) == 0 and color.name().upper() == "#FFFFFF":
                width *= 0.9
        except Exception:
            pass

        if pat_len == 0 and pat_arr:
            symbol = QgsLineSymbol()
            interval = max((sum(pat_arr) / 100.0) * density, 0.05)
            offset = 0.0
            try:
                if pattern_offset is not None:
                    offset = max((float(pattern_offset) / 100.0) * density, 0.0)
            except Exception:
                offset = 0.0

            marker_layer = QgsMarkerLineSymbolLayer(True, interval)
            marker_layer.setOutputUnit(QgsUnitTypes.RenderMapUnits)
            marker_layer.setInterval(interval)
            marker_layer.setIntervalUnit(QgsUnitTypes.RenderMapUnits)
            marker_layer.setOffsetAlongLine(offset)
            marker_layer.setOffsetAlongLineUnit(QgsUnitTypes.RenderMapUnits)

            marker_symbol = QgsMarkerSymbol.createSimple(
                {
                    "name": "circle",
                    "color": color.name(),
                    "outline_color": color.name(),
                    "outline_width": "0",
                    "size": f"{max(width, 0.05):.3f}",
                }
            )
            marker_symbol.setOutputUnit(QgsUnitTypes.RenderMapUnits)
            marker_layer.setSubSymbol(marker_symbol)
            symbol.changeSymbolLayer(0, marker_layer)
            symbol.setOutputUnit(QgsUnitTypes.RenderMapUnits)
            return symbol

        symbol = QgsLineSymbol.createSimple(
            {
                "line_color": color.name(),
                "line_width": f"{width:.3f}",
            }
        )
        layer = symbol.symbolLayer(0)
        symbol.setOutputUnit(QgsUnitTypes.RenderMapUnits)
        try:
            layer.setOutputUnit(QgsUnitTypes.RenderMapUnits)
        except Exception:
            pass
        try:
            if str(line_cap or "").strip() == "Abgeschnitten":
                layer.setPenCapStyle(Qt.PenCapStyle.FlatCap)
            else:
                layer.setPenCapStyle(Qt.PenCapStyle.RoundCap)
        except Exception:
            pass
        if pat_len > 0 and pat_arr:
            try:
                dash = [max((pat_len / 100.0) * density, 0.05)]
                dash.extend(max((value / 100.0) * density, 0.05) for value in pat_arr)
                layer.setUseCustomDashPattern(True)
                layer.setCustomDashVector(dash)
            except Exception:
                pass

        return symbol

    def _polygon_symbol_props_for_theme(self, theme: str) -> dict[str, str]:
        normalized = theme.lower()
        if "gebäude" in normalized or "bauteil" in normalized:
            return {
                "color": "#e7e3db",
                "outline_color": "#6b7280",
                "outline_width": "0.18",
            }
        if any(token in normalized for token in ["verkehr", "strassen", "straßen", "platz", "weg"]):
            return {
                "color": "#f3ede2",
                "outline_color": "#ccaf7f",
                "outline_width": "0.14",
            }
        if any(token in normalized for token in ["gewässer", "wasser"]):
            return {
                "color": "#dceefe",
                "outline_color": "#4f93c5",
                "outline_width": "0.16",
            }
        if "rechtliche festlegungen" in normalized:
            return {
                "color": "255,255,255,0",
                "outline_color": "#d97706",
                "outline_width": "0.20",
            }
        return {
            "color": "#e4edd9",
            "outline_color": "#86a66e",
            "outline_width": "0.12",
        }

    def _line_symbol_props_for_theme(self, theme: str) -> dict[str, str]:
        normalized = theme.lower()
        if "gebäude" in normalized or "bauteil" in normalized:
            return {"line_color": "#5f6368", "line_width": "0.38"}
        if any(token in normalized for token in ["verkehr", "strassen", "straßen", "platz", "weg"]):
            return {"line_color": "#8b6a43", "line_width": "0.34"}
        if any(token in normalized for token in ["gewässer", "wasser"]):
            return {"line_color": "#2f7eb9", "line_width": "0.36"}
        if "rechtliche festlegungen" in normalized:
            return {"line_color": "#d97706", "line_width": "0.30"}
        return {"line_color": "#475569", "line_width": "0.28"}

    def _apply_polygon_style(self, layer: QgsVectorLayer) -> None:
        fields = self._field_names(layer)
        if "thema" not in fields:
            layer.setRenderer(
                QgsRuleBasedRenderer(
                    QgsFillSymbol.createSimple(
                        {
                            "color": "#ebe6df",
                            "outline_color": "#8a8f98",
                            "outline_width": "0.15",
                        }
                    )
                )
            )
            return

        root_rule = QgsRuleBasedRenderer(QgsFillSymbol.createSimple({"color": "#ebe6df"})).rootRule()
        root_rule.children().clear()
        rules = [
            (
                "Gebäude und Bauteile",
                "\"thema\" ILIKE '%Gebäude%' OR \"thema\" ILIKE '%Bauteil%'",
                {
                    "color": "#e7e3db",
                    "outline_color": "#6b7280",
                    "outline_width": "0.18",
                },
            ),
            (
                "Verkehrsflächen",
                "\"thema\" ILIKE '%Verkehr%' OR \"thema\" ILIKE '%Strassen%' OR \"thema\" ILIKE '%Straßen%' OR \"thema\" ILIKE '%Platz%' OR \"thema\" ILIKE '%Weg%'",
                {
                    "color": "#f3ede2",
                    "outline_color": "#ccaf7f",
                    "outline_width": "0.14",
                },
            ),
            (
                "Gewässer",
                "\"thema\" ILIKE '%Gewässer%' OR \"thema\" ILIKE '%Wasser%'",
                {
                    "color": "#dceefe",
                    "outline_color": "#4f93c5",
                    "outline_width": "0.16",
                },
            ),
            (
                "Rechtliche Festlegungen",
                "\"thema\" = 'Rechtliche Festlegungen'",
                {
                    "color": "255,255,255,0",
                    "outline_color": "#d97706",
                    "outline_style": "dash",
                    "outline_width": "0.20",
                },
            ),
            (
                "Sonstige Flächen",
                "ELSE",
                {
                    "color": "#e4edd9",
                    "outline_color": "#86a66e",
                    "outline_width": "0.12",
                },
            ),
        ]
        for label, expression, symbol_props in rules:
            symbol = QgsFillSymbol.createSimple(symbol_props)
            rule = root_rule.children()[0].clone() if root_rule.children() else QgsRuleBasedRenderer.Rule(symbol)
            rule.setSymbol(symbol)
            rule.setLabel(label)
            rule.setFilterExpression(None if expression == "ELSE" else expression)
            rule.setElse(expression == "ELSE")
            root_rule.appendChild(rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        renderer.setOrderByEnabled(False)
        layer.setRenderer(renderer)

    def _apply_line_style(self, layer: QgsVectorLayer) -> None:
        fields = self._field_names(layer)
        if "thema" not in fields:
            layer.setRenderer(
                QgsRuleBasedRenderer(
                    QgsLineSymbol.createSimple({"line_color": "#485569", "line_width": "0.32"})
                )
            )
            return

        root_rule = QgsRuleBasedRenderer(QgsLineSymbol.createSimple({"line_color": "#485569"})).rootRule()
        root_rule.children().clear()
        rules = [
            (
                "Gebäude",
                "\"thema\" ILIKE '%Gebäude%' OR \"thema\" ILIKE '%Bauteil%'",
                {"line_color": "#5f6368", "line_width": "0.38"},
            ),
            (
                "Verkehr",
                "\"thema\" ILIKE '%Verkehr%' OR \"thema\" ILIKE '%Strassen%' OR \"thema\" ILIKE '%Straßen%' OR \"thema\" ILIKE '%Platz%' OR \"thema\" ILIKE '%Weg%'",
                {"line_color": "#8b6a43", "line_width": "0.34"},
            ),
            (
                "Gewässer",
                "\"thema\" ILIKE '%Gewässer%' OR \"thema\" ILIKE '%Wasser%'",
                {"line_color": "#2f7eb9", "line_width": "0.36"},
            ),
            (
                "Rechtliche Festlegungen",
                "\"thema\" = 'Rechtliche Festlegungen'",
                {"line_color": "#d97706", "line_width": "0.30", "line_style": "dash"},
            ),
            (
                "Sonstige Linien",
                "ELSE",
                {"line_color": "#475569", "line_width": "0.28"},
            ),
        ]
        for label, expression, symbol_props in rules:
            symbol = QgsLineSymbol.createSimple(symbol_props)
            rule = root_rule.children()[0].clone() if root_rule.children() else QgsRuleBasedRenderer.Rule(symbol)
            rule.setSymbol(symbol)
            rule.setLabel(label)
            rule.setFilterExpression(None if expression == "ELSE" else expression)
            rule.setElse(expression == "ELSE")
            root_rule.appendChild(rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        renderer.setOrderByEnabled(False)
        layer.setRenderer(renderer)

    def _apply_point_style(self, layer: QgsVectorLayer) -> None:
        fields = self._field_names(layer)
        svg_renderer = self._build_svg_point_renderer(layer, fields)
        if svg_renderer is not None:
            layer.setRenderer(svg_renderer)
            return

        root_rule = QgsRuleBasedRenderer(QgsMarkerSymbol.createSimple({"name": "circle"})).rootRule()
        root_rule.children().clear()
        rules = [
            (
                "Gebäude",
                "\"thema\" ILIKE '%Gebäude%' OR \"thema\" ILIKE '%Bauteil%'",
                {
                    "name": "square",
                    "color": "#7c8188",
                    "outline_color": "#ffffff",
                    "outline_width": "0.3",
                    "size": "2.3",
                },
            ),
            (
                "Verkehr",
                "\"thema\" ILIKE '%Verkehr%' OR \"thema\" ILIKE '%Strassen%' OR \"thema\" ILIKE '%Straßen%' OR \"thema\" ILIKE '%Platz%' OR \"thema\" ILIKE '%Weg%'",
                {
                    "name": "triangle",
                    "color": "#976a34",
                    "outline_color": "#ffffff",
                    "outline_width": "0.3",
                    "size": "2.4",
                },
            ),
            (
                "Gewässer",
                "\"thema\" ILIKE '%Gewässer%' OR \"thema\" ILIKE '%Wasser%'",
                {
                    "name": "circle",
                    "color": "#3f93d1",
                    "outline_color": "#ffffff",
                    "outline_width": "0.3",
                    "size": "2.5",
                },
            ),
            (
                "Sonstige Punkte",
                "ELSE",
                {
                    "name": "circle",
                    "color": "#0f172a",
                    "outline_color": "#ffffff",
                    "outline_width": "0.25",
                    "size": "2.1",
                },
            ),
        ]

        for label, expression, symbol_props in rules:
            symbol = QgsMarkerSymbol.createSimple(symbol_props)
            if "rotation" in fields:
                symbol.setDataDefinedAngle(QgsProperty.fromField("rotation"))
            rule = root_rule.children()[0].clone() if root_rule.children() else QgsRuleBasedRenderer.Rule(symbol)
            rule.setSymbol(symbol)
            rule.setLabel(label)
            if "thema" in fields and expression != "ELSE":
                rule.setFilterExpression(expression)
            else:
                rule.setFilterExpression(None)
            rule.setElse(expression == "ELSE" or "thema" not in fields)
            root_rule.appendChild(rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        renderer.setOrderByEnabled(False)
        layer.setRenderer(renderer)

    def _build_svg_point_renderer(
        self,
        layer: QgsVectorLayer,
        fields: set[str],
    ) -> QgsCategorizedSymbolRenderer | None:
        if "svg_filename" not in fields:
            return None

        filenames: list[str] = []
        seen: set[str] = set()
        for feature in layer.getFeatures():
            filename = str(feature["svg_filename"] or "").strip()
            if not filename or filename in seen:
                continue
            if self._resolve_svg_path(filename) is None:
                continue
            seen.add(filename)
            filenames.append(filename)

        if not filenames:
            return None

        categories: list[QgsRendererCategory] = []
        for filename in sorted(filenames):
            svg_path = self._resolve_svg_path(filename)
            if svg_path is None:
                continue
            symbol = QgsMarkerSymbol()
            symbol.changeSymbolLayer(0, QgsSvgMarkerSymbolLayer(svg_path, 4.0, 0.0))
            if "rotation" in fields:
                symbol.setDataDefinedAngle(QgsProperty.fromField("rotation"))
            categories.append(QgsRendererCategory(filename, symbol, filename))

        if not categories:
            return None

        return QgsCategorizedSymbolRenderer("svg_filename", categories)

    def _resolve_svg_path(self, filename: str) -> str | None:
        candidate = os.path.join(self.plugin.plugin_dir, "svg", filename)
        return candidate if os.path.exists(candidate) else None

    def _apply_label_style(self, layer: QgsVectorLayer) -> None:
        geometry_type = layer.geometryType()
        if geometry_type == 0:
            layer.setRenderer(
                QgsRuleBasedRenderer(
                    QgsMarkerSymbol.createSimple(
                        {"name": "circle", "size": "0.01", "color": "255,255,255,0", "outline_style": "no"}
                    )
                )
            )
        elif geometry_type == 1:
            layer.setRenderer(
                QgsRuleBasedRenderer(
                    QgsLineSymbol.createSimple({"line_color": "255,255,255,0", "line_width": "0"})
                )
            )

        fields = self._field_names(layer)
        label_field = "text_content" if "text_content" in fields else ("text" if "text" in fields else None)
        if not label_field:
            return

        pal = QgsPalLayerSettings()
        pal.enabled = True
        pal.fieldName = label_field
        if geometry_type == 1:
            pal.placement = QgsPalLayerSettings.Curved
        elif geometry_type == 0:
            pal.placement = QgsPalLayerSettings.OverPoint
        else:
            pal.placement = QgsPalLayerSettings.Horizontal

        text_format = QgsTextFormat()
        font = QFont("Arial")
        font.setPointSizeF(9.0)
        text_format.setFont(font)
        text_format.setSize(9.0)
        text_format.setSizeUnit(QgsUnitTypes.RenderPoints)
        text_format.setColor(QColor("#111827"))

        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setColor(QColor("#ffffff"))
        buffer_settings.setSize(1.0)
        buffer_settings.setSizeUnit(QgsUnitTypes.RenderPoints)
        text_format.setBuffer(buffer_settings)
        pal.setFormat(text_format)

        rotation_field = "raw_rotation" if "raw_rotation" in fields else ("rotation" if "rotation" in fields else None)
        if rotation_field:
            pal.rotationFieldName = rotation_field

        layer.setLabelsEnabled(True)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))


class LageplanerPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.action: QAction | None = None
        self.dialog: LageplanerDialog | None = None
        self.plugin_dir = os.path.dirname(__file__)
        self.icon_path = os.path.join(self.plugin_dir, "icon.png")

    def initGui(self) -> None:
        self.action = QAction(QIcon(self.icon_path), "Lageplaner", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Lageplaner", self.action)

    def unload(self) -> None:
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&Lageplaner", self.action)
            self.action = None

    def run(self) -> None:
        if self.dialog is None:
            self.dialog = LageplanerDialog(self)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
