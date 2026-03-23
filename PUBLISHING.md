# Publishing Checklist

## Ziel

`Lageplaner` auf `plugins.qgis.org` veroeffentlichen und dort moeglichst gut auffindbar machen.

## Aktueller Store-Text

### Name

`Lageplaner`

### Kurzbeschreibung

`Load ALKIS cadastral data for the current map extent directly into QGIS.`

### Lange Beschreibung

`ALKIS-Daten für den aktuellen Kartenausschnitt direkt in QGIS laden.

Lädt ALKIS-Daten für den aktuellen Kartenausschnitt direkt in QGIS, inklusive Farben, Stricharten, Symbolen und Beschriftungen. Datenstand und Lizenzen je Bundesland finden Sie unter lageplaner.de/quelldaten. Aktuell ohne Bayern und Sachsen-Anhalt.`

### Tags

- `alkis`
- `cadastre`
- `cadastral`
- `geopackage`
- `parcels`
- `buildings`
- `land use`
- `germany`
- `qgis`

## Was noch vor dem Upload fehlt

### 1. Echte Repository-URL

`metadata.txt` verlangt fuer den offiziellen QGIS-Upload eine gueltige `repository`-URL.

Empfehlung:
- GitHub-Repo fuer das Plugin anlegen
- dort `README.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md` und das Plugin selbst veroeffentlichen

### 2. Tracker-URL

Empfehlung:
- GitHub Issues verwenden
- `tracker` auf die Issues-URL setzen

### 3. Lizenz des Plugins final klaeren

Aktuell gibt es noch echte Publish-Blocker:
- die SVG-Symbole stammen aus dem norBIT-Plugin

Vor Upload sauber entscheiden:
- Plugin-Code und verteilte Assets unter einer GPL-kompatiblen Lizenz
- SVG-Lizenz und Plugin-Lizenz konsistent dokumentieren

Empfehlung fuer den aktuellen Stand:
- Plugin als `GPL-2.0-only` veroeffentlichen
- `LICENSE` im Repo-Root mitliefern
- in README und Drittanbieterhinweisen klar auf die norBIT-SVGs verweisen

### 4. `experimental=False`

Erst setzen, wenn:
- Lizenz geklaert
- Repository gesetzt
- Tracker gesetzt
- mindestens ein kurzer Test auf zwei QGIS-Versionen erledigt ist

## Empfohlene Screenshots fuer `plugins.qgis.org`

- Plugin-Dialog mit `Layer laden`
- importierte ALKIS-Daten mit Flaechen, Linien, Punkten und Beschriftungen
- Detailansicht mit SVG-Symbolen
- Layerbaum mit Signaturnummern und Bezeichnungen

## Auffindbarkeit in QGIS verbessern

Die QGIS-Plugin-Suche lebt vor allem von:
- `name`
- `description`
- `about`
- `tags`

Deshalb sinnvoll:
- englische Kurzbeschreibung fuer die Suche
- klare Fachbegriffe wie `ALKIS`, `cadastre`, `cadastral`, `parcels`, `buildings`, `geopackage`
- auf den ersten Screenshots direkt sichtbare ALKIS-Darstellung

## Upload-Schritte

1. Account auf `plugins.qgis.org` anlegen
2. Plugin-ZIP hochladen:
   - `dist/lageplaner-qgis-plugin.zip`
3. Beschreibung und Screenshots im Plugin-Portal pflegen
4. nach Freigabe in QGIS Plugin Manager suchen und Installierbarkeit testen

## Empfohlenes GitHub-Setup

### Repository-Name

- `lageplaner-qgis-plugin`

### Sichtbarkeit

- oeffentlich

### Wichtige Dateien im Repo-Root

- `README.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `PUBLISHING.md`

### Repository-URL in `metadata.txt`

Sobald das Repo existiert, eintragen:

- `repository=https://github.com/<org-or-user>/lageplaner-qgis-plugin`

### Tracker-URL in `metadata.txt`

Sobald GitHub Issues aktiv ist, eintragen:

- `tracker=https://github.com/<org-or-user>/lageplaner-qgis-plugin/issues`

## Offizielle Referenzen

- QGIS Publish Docs:
  - https://plugins.qgis.org/docs/publish
- PyQGIS Plugin Metadata Docs:
  - https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html
