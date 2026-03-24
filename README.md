# Lageplaner QGIS Plugin

Mit dem Lageplaner-Plugin lassen sich ALKIS-Katasterdaten für den aktuellen Kartenausschnitt direkt in QGIS laden.

Der sichtbare Ausschnitt wird als GeoPackage aus der Lageplaner API geladen und anschließend mit Farben, Linienarten, Symbolen und Beschriftungen in QGIS dargestellt.

Der öffentliche GeoPackage-Zugang ist auf 1 km² pro Export begrenzt. Zusätzlich gelten 30 Anfragen pro Stunde pro IP-Adresse und maximal 2 gleichzeitige Jobs pro IP-Adresse.

Datenstand und Lizenzhinweise je Bundesland:
[lageplaner.de/quelldaten](https://lageplaner.de/quelldaten)

API-Dokumentation:
[api.lageplaner.de/v1/docs](https://api.lageplaner.de/v1/docs)

Derzeit noch nicht verfügbar:
- Bayern
- Sachsen-Anhalt

English summary: Load ALKIS cadastral data for the current map extent into QGIS.

## Lizenz

Das Plugin wird mit einer GPL-2.0-Lizenzdatei ausgeliefert:

- [LICENSE](./LICENSE)

Der praktische Grund dafür ist die mitgelieferte SVG-Symbolbibliothek aus dem norBIT-ALKIS-Plugin. Solange diese Symbole Teil des Plugin-Pakets sind, ist GPL-2.0 für den Release-Stand die sicherste Wahl.

## Was das Plugin macht

- übernimmt den aktuellen Kartenausschnitt aus QGIS
- lädt ALKIS-Daten als GeoPackage aus der Lageplaner API
- legt Flächen, Linien, Punkte und Beschriftungen direkt im Projekt an
- nutzt passende Farben, Linienstile, SVG-Symbole und Beschriftungen
- benennt Layer nachvollziehbar nach Signaturnummer und Bezeichnung
- funktioniert ohne eigenen API-Key

## Installieren in QGIS

1. Den Ordner `lageplaner` zippen.
2. In QGIS: `Plugins` -> `Plugins verwalten und installieren...`
3. `Aus ZIP installieren` wählen.
4. Das erzeugte ZIP auswählen.

Wichtig: Die ZIP muss direkt den Plugin-Ordner `lageplaner` enthalten.

## Hinweise

- Maximale Exportfläche: `1 km²`
- Maximale Anzahl öffentlicher Anfragen: `30 pro Stunde pro IP-Adresse`
- Maximale Anzahl gleichzeitiger öffentlicher Jobs: `2 pro IP-Adresse`
- Unterstützte Standorte: nur Deutschland mit verfügbarem ALKIS-Datensatz
- Datenstand und Lizenzen je Bundesland:
  - [lageplaner.de/quelldaten](https://lageplaner.de/quelldaten)
- API-Dokumentation:
  - [api.lageplaner.de/v1/docs](https://api.lageplaner.de/v1/docs)

Typische Rückmeldungen:

- `NO_DATA`
  - für den gewählten Standort steht derzeit kein unterstützter Datensatz bereit
- `STATE_PROBE_FAILED`
  - technischer Fehler bei der Datensatzprüfung

## Symbolik

Das Plugin bringt eine automatische QGIS-Symbolik mit:

- Flächen, Linien und Punkte werden anhand von Darstellungsattributen, Signaturnummern und SVG-Symbolen dargestellt.
- Beschriftungen werden direkt aus dem Label-Layer aktiviert.
- Wenn im Layer das Feld `svg_filename` vorhanden ist und im Plugin unter `lageplaner/svg/` eine gleichnamige SVG-Datei liegt, nutzt das Plugin automatisch diese SVG statt des generischen Punktsymbols.

Damit ist der saubere Zielzustand:

- API liefert die Daten und `svg_filename`
- Plugin liefert die SVG-Dateien und die QGIS-Darstellung

## Herkunft der SVG-Symbole

Das Plugin enthält derzeit die SVG-Symbolbibliothek aus dem norBIT-Repository:

- https://github.com/norBIT/alkisplugin

Die Symbole liegen im Plugin unter `lageplaner/svg/`.
Ein Lizenzhinweis liegt in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).

## Öffentlicher Plugin-Zugang

Das Plugin nutzt den öffentlichen GeoPackage-Zugang der Lageplaner API.

- kein API-Key erforderlich
- begrenzt auf `1 km²` pro Export
- begrenzt auf `30` Anfragen pro Stunde pro IP-Adresse
- begrenzt auf `2` gleichzeitige Jobs pro IP-Adresse
- nur für GeoPackage-Exporte
- für Deutschland mit verfügbaren ALKIS-Datensätzen
- API-Dokumentation:
  - [api.lageplaner.de/v1/docs](https://api.lageplaner.de/v1/docs)
