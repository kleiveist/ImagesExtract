# Changelog

Alle wesentlichen Änderungen an ImagesExtract werden in dieser Datei
dokumentiert. Das Format orientiert sich an
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/); die geplante
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

## [0.1.0] - 2026-08-29

### Hinzugefügt

- Installierbares `src`-Paket und zentraler `images-extract`-CLI-Einstiegspunkt.
- Befehle `run`, `stage`, `doctor` und `validate-config`.
- Expliziter `RunContext` mit isolierten Run-Verzeichnissen.
- Einheitlicher `StageResult`- und Pipeline-Ergebnisvertrag.
- Atomare Bild-, Kopier- und Manifest-Schreibvorgänge.
- JSON-Manifest mit Eingaben, Prüfsummen, Konfiguration und Stufenergebnissen.
- TOML-Konfiguration mit zentral definierten Rezepten.
- Übergangsloader für historische `settings.ini`-Dateien.
- Unit-, Integrations-, CLI- und Regressionstests.
- CI-Prüfungen für Ruff, pytest, Paketbau sowie Ubuntu-/CachyOS-Fish-Quick-Starts.
- Reproduzierbarer, rein informativer Pipeline-Benchmark.

### Geändert

- PNG/RGBA ist das verbindliche interne Arbeitsformat.
- Pfade werden ausschließlich aus CLI und `RunContext` bezogen.
- Interne Stufen laufen als Funktionen im selben Python-Prozess.
- Rezeptzweige ersetzen die über einzelne Skripte verteilten
  Collation-Schalter.
- Skalierung und Collation erkennen Namenskollisionen vor dem Schreiben.
- Bildreihenfolge und zufallsbasierte Verarbeitung sind deterministisch.
- README und Prozessdokumentation entsprechen der tatsächlichen CLI.
- Der aktive Branch enthält keine destruktive Legacy-Ausführung, eingecheckten
  Logs oder Python-Caches mehr; der Altstand bleibt über den Legacy-Tag verfügbar.

### Sicherheit

- Quellen bleiben standardmäßig unverändert.
- Überschreiben, Verschieben von Quellen und Löschen von Zwischenständen sind
  nur mit ausdrücklichen CLI-Optionen möglich.
- Leere Eingaben verändern keine vorhandenen Runs.
- Gleiche Basisnamen überschreiben einander nicht mehr still.
- Portable Case-/Unicode-Kollisionen, Symlink-Ziele und konkurrierende
  No-Clobber-Schreibvorgänge werden sicher behandelt.

## Legacy-Baseline – 2026-08-29

- Der unveränderte historische Stand ist mit dem annotierten Tag
  `legacy-baseline-2026-08-29` gesichert.
- Die Wiederherstellung erfolgt auf `restore/2026-08-29`.
