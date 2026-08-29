# ImagesExtract

ImagesExtract ist eine reproduzierbare, nicht-destruktive Kommandozeilen-Pipeline
für Rasterbilder. Sie liest WebP-, PNG-, JPEG-, BMP- und TIFF-Dateien ein,
verarbeitet sie über explizite Rezepte und verwendet PNG/RGBA als verbindliches
Arbeitsformat.

Das Repository wurde aus der gesicherten Legacy-Baseline vom 29. August 2026
kontrolliert wiederhergestellt. Der CI-Status wird erst nach einem tatsächlich
ausgeführten Workflow ausgewiesen.

## Sicherheitsversprechen

- Eingabedateien bleiben standardmäßig unverändert.
- Jeder Lauf besitzt eine eindeutige Run-ID und ein eigenes Verzeichnis.
- Dateien werden zunächst temporär geschrieben, validiert und anschließend atomar
  veröffentlicht.
- Vorhandene Ziele werden ohne `--overwrite` nicht überschrieben.
- Namenskollisionen führen standardmäßig vor der Verarbeitung zu einem Fehler.
- Ein leerer Input verändert weder alte Runs noch deren Manifestdateien.
- Interne Stufen werden im selben Python-Prozess ausgeführt; die Pipeline hängt
  nicht vom aktuellen Arbeitsverzeichnis ab.

Die Optionen `--move-sources`, `--overwrite` und `--delete-intermediates` lockern
diese Garantien ausdrücklich. Verwende sie nur, wenn die betreffenden Daten
anderweitig gesichert sind.

## Voraussetzungen

- Python 3.11 oder neuer
- Git
- Fish für den folgenden Fish-Quick-Start

Pillow, NumPy und OpenCV werden über das Paket-Metadatenmodell installiert. Eine
manuell anzulegende `requirements.txt` ist nicht erforderlich.

## Quick Start mit Fish

```fish
git clone https://github.com/kleiveist/ImagesExtract.git
cd ImagesExtract

python -m venv .venv
source .venv/bin/activate.fish

python -m pip install --upgrade pip
python -m pip install -e .

images-extract doctor
images-extract run ~/Bilder/input \
    --output ~/Bilder/image_ext
```

Für einen reproduzierbaren Lauf mit den eingecheckten Beispieldaten:

```fish
images-extract run examples/input --output /tmp/images-extract-test
```

Unter Bash lautet die Aktivierung `source .venv/bin/activate`. Unter Windows
PowerShell kann `.venv\Scripts\Activate.ps1` verwendet werden.

## CLI

### Gesamte Pipeline ausführen

```text
images-extract run INPUT --output OUTPUT [--config FILE]
```

Beispiele:

```fish
images-extract run ./input --output ./image_ext
images-extract run ./input --output ./image_ext --config ./images-extract.toml
images-extract run ./input --output ./image_ext --recipe transback --recipe whitepaper
```

Wichtige Optionen:

| Option | Bedeutung |
| --- | --- |
| `--workers N` | Verarbeitet mit `N` Workern; Standard ist 1, maximal `min(max_workers, 32)`. |
| `--recipe NAME` | Aktiviert ein Rezept; die Option darf wiederholt werden. |
| `--collision error\|suffix\|hash` | Legt die Strategie für gleiche Zielnamen fest. |
| `--allow-empty` | Behandelt einen leeren Input bewusst als übersprungenen Erfolg. |
| `--run-id ID` | Vergibt eine nachvollziehbare Run-ID statt einer automatisch erzeugten. |
| `--move-sources` | Verschiebt Quellen ausdrücklich statt sie unverändert zu lassen. |
| `--overwrite` | Erlaubt das Ersetzen bereits vorhandener Ziele. |
| `--delete-intermediates` | Entfernt Zwischenprodukte nach erfolgreichem Abschluss. |
| `--verbose` | Gibt zusätzliche Laufdetails auf der Konsole aus. |

### Einzelne Stufe ausführen

```text
images-extract stage STAGE INPUT --output OUTPUT
```

Die verfügbaren Stufen heißen `convert`, `enhance`, `transparency`, `extract`,
`extract_gray`, `cleanup`, `colors`, `invert`, `scale` und `collate`.

```fish
images-extract stage convert ./input --output ./converted
images-extract stage transparency ./converted --output ./transparent
```

Auch `stage` akzeptiert `--config FILE`, `--workers N`, `--overwrite` und eine
Kollisionsstrategie. `--collision` wirkt dort ausschließlich bei `convert`.

### Installation und Umgebung prüfen

```text
images-extract doctor
```

`doctor` prüft die Python-Umgebung, importierbare Bildabhängigkeiten und die
verwendbare Standardkonfiguration, ohne Eingabebilder zu verändern.
Mit `images-extract doctor --config FILE` wird stattdessen die angegebene TOML-
oder Legacy-INI-Datei geprüft.

### Konfiguration prüfen

```text
images-extract validate-config
```

Die Validierung endet vor jeglicher Bildverarbeitung. Ungültige Schwellenwerte,
Skalen, Farben, Rezepte oder Workerzahlen werden mit dem betroffenen Feld
gemeldet. Eine eigene Datei wird mit
`images-extract validate-config --config FILE` validiert.

## Eingabe- und Ausgabeformat

| Phase | Vertrag |
| --- | --- |
| Eingabe | WebP, PNG, JPG/JPEG, BMP, TIF/TIFF |
| Arbeitsformat | PNG mit explizitem RGBA-Kanal |
| Endexport | zunächst PNG; weitere Formate gehören in eine spätere Exportstufe |

RGB- und Graustufenbilder werden beim Import kontrolliert nach RGBA normalisiert.
Transparenz wird erhalten. Beschädigte oder nicht lesbare Bilder werden im
Stufenergebnis gezählt und führen zu einem fehlgeschlagenen Gesamtstatus.

## Runs, Ergebnisse und Manifest

Ein normaler Lauf erzeugt folgende isolierte Struktur:

```text
OUTPUT/
└── runs/
    └── 20260829-231500-a31f/
        ├── working/
        ├── recipes/
        ├── scales/
        ├── collation/
        └── manifest.json
```

Das Manifest enthält mindestens Run-ID, Zeitstempel, normalisierte Optionen,
Eingaben mit Prüfsummen, die aufgelöste Konfiguration sowie für jede Stufe Status,
Zähler, Laufzeit, Ausgaben und Fehler. Ein Stufenstatus ist `success`, `skipped`
oder `failed`.

## Kollisionsregeln

Wenn etwa `icon.jpg` und `icon.webp` beide zu `icon.png` würden, greift die
gewählte Strategie:

- `error` ist der sichere Standard und bricht vor dem Schreiben ab.
- `suffix` erzeugt deterministisch nummerierte Namen.
- `hash` ergänzt einen kurzen, aus der Quelle abgeleiteten Hash.

Keine Strategie überschreibt still eine bereits vorhandene Datei. Dazu wäre
zusätzlich die ausdrückliche Option `--overwrite` erforderlich.

## Exitcodes

| Code | Bedeutung |
| ---: | --- |
| `0` | vollständig erfolgreich oder mit `--allow-empty` bewusst übersprungen |
| `1` | mindestens eine Verarbeitungsstufe ist fehlgeschlagen |
| `2` | ungültiger Aufruf oder ungültige Konfiguration |

„Keine Eingabedateien“ ist ohne `--allow-empty` ein klarer Fehler vor dem
Anlegen eines Runs.

## Rezepte und Konfiguration

Rezepte definieren zentral, welche Stufen ein Ergebniszweig durchläuft. Eine
Stufe enthält keine fest verdrahtete Kenntnis über historische
„Collation 1 bis 7“-Ordner. Die Standardkonfiguration aktiviert nur das Rezept
`transback`; weitere Rezepte werden in der TOML-Datei oder über `--recipe`
zugeschaltet.

Ausgangspunkt für eine eigene TOML-Datei ist
[`images-extract.example.toml`](images-extract.example.toml); die vollständige
Referenz steht in [docs/configuration.md](docs/configuration.md). Historische
`settings.ini`-Dateien werden während der Übergangsphase einschließlich der alten
`output_foldes_collation*`-Schlüssel eingelesen und auf das neue Modell
abgebildet. Neue Konfigurationen sollten TOML verwenden.

## Architektur und Prozess

- [Architektur, StageResult und RunContext](docs/architecture.md)
- [Konfigurationsreferenz und Legacy-Migration](docs/configuration.md)
- [Verarbeitungsrezepte und Beispielbilder](docs/process.md)
- [Performance- und Benchmarkregeln](docs/performance.md)
- [Wiederherstellungs- und Abnahmebericht](docs/restoration-report.md)

Die frühere Skriptsammlung und der alte Master-Runner sind vollständig im Tag
`legacy-baseline-2026-08-29` gesichert. Der unterstützte Einstiegspunkt ist
ausschließlich die installierte `images-extract`-CLI.

## Entwicklung

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

Der GitHub-Workflow prüft die vorgesehenen Python-Versionen, Ruff, pytest, den
Wheel-Einbau in eine frische Umgebung sowie den dokumentierten Fish-Smoke-Test
auf Ubuntu und zusätzlich im
[offiziellen CachyOS-Container](https://github.com/CachyOS/docker).
Ein Badge wird erst ergänzt, nachdem dieser Workflow tatsächlich gelaufen ist.

Details für Beiträge stehen in [CONTRIBUTING.md](CONTRIBUTING.md); Änderungen
werden in [CHANGELOG.md](CHANGELOG.md) dokumentiert.

## Lizenz

ImagesExtract steht unter der [MIT-Lizenz](LICENSE.md).
