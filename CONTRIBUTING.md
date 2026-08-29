# Zu ImagesExtract beitragen

Danke für dein Interesse an ImagesExtract. Änderungen sollen die zentralen
Eigenschaften des Projekts erhalten: nachvollziehbare Pfade, deterministische
Ergebnisse, unveränderte Quellen und atomare Ausgaben.

## Entwicklungsumgebung

```bash
git clone https://github.com/kleiveist/ImagesExtract.git
cd ImagesExtract
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Fish verwendet stattdessen:

```fish
source .venv/bin/activate.fish
```

## Vor einer Änderung

1. Lege ein konkretes GitHub-Issue an oder verknüpfe die Änderung mit einem
   vorhandenen Ticket.
2. Erstelle einen kleinen, thematisch begrenzten Branch.
3. Neue Implementierung gehört unter `src/images_extract/`; historische Quellen
   sind über den Legacy-Tag verfügbar und werden nicht zurückkopiert.
4. Verwende weder echte Kundendaten noch vertrauliche Bilder als Fixture.

## Lokale Prüfungen

```bash
ruff check .
ruff format --check .
pytest
python -m build
```

Vor Änderungen am Quick Start sollte zusätzlich der dokumentierte Ablauf in
einer frischen virtuellen Umgebung getestet werden:

```bash
images-extract doctor
images-extract run examples/input --output /tmp/images-extract-check
```

## Testregeln

- Jeder Bugfix benötigt einen Test, der vor der Korrektur fehlschlägt.
- Tests dürfen nicht vom aktuellen Arbeitsverzeichnis, der Uhrzeit oder einer
  zufälligen Dateisystemreihenfolge abhängen.
- Zufallsbasierte Algorithmen erhalten einen festen Seed.
- RGB, RGBA und echte Graustufenbilder werden getrennt geprüft.
- Dateisicherheitstests vergleichen Quellprüfsummen vor und nach dem Lauf.
- Ein zweiter identischer Lauf muss ohne Namens- oder Ordnereskalation enden.
- Exakte Pixel-Golden-Files sind nur sinnvoll, wenn das Ergebnis über alle
  unterstützten Plattformen stabil ist. Ansonsten werden Bildinvarianten oder
  dokumentierte Toleranzen geprüft.

Kleine synthetische Fixtures sollten im Test erzeugt werden. Dauerhaft
eingecheckte Beispielbilder gehören nach `examples/input`, erwartete Verträge
nach `examples/expected`.

## Stage-Vertrag

Neue Stufen müssen:

- ausschließlich explizite Eingaben und einen `RunContext` verwenden,
- einen `StageResult` mit `success`, `skipped` oder `failed` liefern,
- Fehler in den Gesamtstatus einfließen lassen,
- Zielpfade vor dem Schreiben auf Kollisionen prüfen,
- Ausgaben temporär schreiben, validieren und atomar veröffentlichen,
- deterministisch sortierte Ausgaben und Manifestdaten erzeugen.

Eine Stufe darf den Prozess nicht selbst mit `exit()` beenden.

## Dokumentation

- Öffentliche CLI- oder Config-Änderungen benötigen gleichzeitig eine Anpassung
  von README und Referenzdokumentation.
- Verwende normales GitHub-Markdown statt Obsidian-Einbettungen.
- Relative Bildlinks in `docs/` beginnen mit `img/`.
- Füge keine statischen „passing“-Badges hinzu.

## Benchmarks

Performanceänderungen werden erst nach bestandenen Korrektheitstests bewertet.
Nutze `benchmarks/benchmark_pipeline.py`, gib Umgebung und JSON-Ergebnis an und
vergleiche 1, 2 und 4 Worker auf demselben Rechner. Ergebnisse geteilter
CI-Runner sind informativ und keine harte Regressionsgrenze.

## Pull-Request-Checkliste

- [ ] Änderung ist auf ein klar abgegrenztes Problem beschränkt.
- [ ] Neue oder geänderte Funktionalität ist getestet.
- [ ] Quellen bleiben im Standardmodus unverändert.
- [ ] Ruff, pytest und Paketbau laufen lokal erfolgreich.
- [ ] README, Config-Referenz und Changelog sind bei öffentlicher Änderung
      aktualisiert.
- [ ] Keine Logs, Caches, Ausgaben, Zugangsdaten oder großen privaten Fixtures
      wurden eingecheckt.
