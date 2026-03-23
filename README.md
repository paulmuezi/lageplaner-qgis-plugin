# Lageplaner QGIS Plugin

ALKIS-Daten für den aktuellen Kartenausschnitt direkt in QGIS laden.

Lädt ALKIS-Daten für den aktuellen Kartenausschnitt direkt in QGIS, inklusive Farben, Stricharten, Symbolen und Beschriftungen. Datenstand und Lizenzen je Bundesland finden Sie unter [lageplaner.de/quelldaten](https://lageplaner.de/quelldaten). Aktuell ohne Bayern und Sachsen-Anhalt.

English summary: Load ALKIS cadastral data for the current map extent directly into QGIS.

## Lizenz

Das Plugin wird mit einer GPL-2.0-Lizenzdatei ausgeliefert:

- [LICENSE](./LICENSE)

Der praktische Grund dafuer ist die mitgelieferte SVG-Symbolbibliothek aus dem norBIT-ALKIS-Plugin. Solange diese Symbole Teil des Plugin-Pakets sind, ist GPL-2.0 fuer den Release-Stand die sicherste Wahl.

## Enthalten

- Plugin-Name: `Lageplaner`
- Lageplaner-Branding mit bestehendem Logo
- Uebernahme des aktuellen QGIS-Kartenausschnitts
- `POST /v1/geopackage`
- Polling auf `GET /v1/geopackage/{task_id}`
- Download des erzeugten `.gpkg`
- immer vollstaendiger Export mit Flaechen, Linien, Punkten und Beschriftungen
- automatisches Laden aller enthaltenen Layer in eine QGIS-Gruppe `Lageplaner`
- automatische Symbolik fuer Flaechen, Linien, Punkte und Beschriftungen
- SVG-Unterstuetzung ueber `lageplaner/svg/` und das Attribut `svg_filename`
- harter API-Endpunkt auf `https://api.lageplaner.de/v1`
- kein API-Key erforderlich
- klare Layernamen nach Signaturnummer und Bezeichnung

## Installieren in QGIS

1. Den Ordner `lageplaner` zippen.
2. In QGIS: `Plugins` -> `Plugins verwalten und installieren...`
3. `Aus ZIP installieren` waehlen.
4. Das erzeugte ZIP auswaehlen.

Wichtig: Die ZIP muss direkt den Plugin-Ordner `lageplaner` enthalten.

## Grenzen und Fehler

- Maximale Exportflaeche: `1 km²`
- Unterstuetzte Standorte: nur Deutschland mit verfuegbarem ALKIS-Datensatz
- Aktuell ohne Bayern und Sachsen-Anhalt
- Datenstand und Lizenzen je Bundesland:
  - [lageplaner.de/quelldaten](https://lageplaner.de/quelldaten)

Typische Fehlercodes:

- `NO_DATA`
  - kein unterstuetzter Datensatz fuer den Standort
  - oder Standort ausserhalb Deutschlands
- `STATE_PROBE_FAILED`
  - technischer Fehler bei der Datensatzpruefung

## Symbolik

Das Plugin bringt eine automatische QGIS-Symbolik mit:

- Flaechen, Linien und Punkte werden anhand von Darstellungsattributen, Signaturnummern und SVG-Symbolen dargestellt.
- Beschriftungen werden direkt aus dem Label-Layer aktiviert.
- Wenn im Layer das Feld `svg_filename` vorhanden ist und im Plugin unter `lageplaner/svg/` eine gleichnamige SVG-Datei liegt, nutzt das Plugin automatisch diese SVG statt des generischen Punktsymbols.

Damit ist der saubere Zielzustand:

- API liefert die Daten und `svg_filename`
- Plugin liefert die SVG-Dateien und die QGIS-Darstellung

## Herkunft der SVG-Symbole

Das Plugin enthaelt derzeit die SVG-Symbolbibliothek aus dem norBIT-Repository:

- https://github.com/norBIT/alkisplugin

Die Symbole liegen im Plugin unter `lageplaner/svg/`.
Ein Lizenzhinweis liegt in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).

## Oeffentlicher Plugin-Zugang

Das Plugin nutzt den oeffentlichen GeoPackage-Zugang der Lageplaner API.

- kein API-Key erforderlich
- begrenzt auf `1 km²` pro Export
- nur fuer GeoPackage-Exporte
- fuer Deutschland mit verfuegbaren ALKIS-Datensaetzen

## Veroeffentlichung

Vor einer Veroeffentlichung auf `plugins.qgis.org` sollten mindestens diese Punkte gesetzt sein:

- `metadata.txt` mit finaler Version, Repository, Tracker und `experimental=False`
- sauberes ZIP ohne `__pycache__`, `.pyc` und `.DS_Store`
- kurzer Screenshot-Satz fuer die Plugin-Seite
- klare Lizenz- und Drittanbieterhinweise fuer SVGs
- kurzer Testlauf auf mindestens QGIS 3.28 und einer aktuellen 3.x-Version

Eine konkrete Checkliste steht in [PUBLISHING.md](./PUBLISHING.md).
