# Performance und Benchmarks

Performance wird erst optimiert, wenn Referenzpipeline, Sicherheitsprüfungen und
Regressionstests bestanden sind. Ein schneller Lauf mit veränderten Quellen oder
nicht reproduzierbaren Resultaten ist keine gültige Verbesserung.

## Ziele

Der Benchmark beantwortet vier Fragen:

1. Welche Stufe benötigt wie viel Laufzeit?
2. Wie verändert sich der Durchsatz mit 1, 2 und 4 Workern?
3. Bleiben Ergebnisse und Manifest unabhängig von der Workerzahl fachlich gleich?
4. Stehen zusätzliche Worker in einem sinnvollen Verhältnis zu CPU-, Speicher-
   und I/O-Aufwand?

## Benchmark ausführen

Nach der Installation des Projekts:

```bash
python benchmarks/benchmark_pipeline.py examples/input \
    --json benchmark-results.json \
    --repeats 3
```

Standardmäßig werden 1, 2 und 4 Worker gemessen. Eine eigene Auswahl ist möglich:

```bash
python benchmarks/benchmark_pipeline.py /pfad/zum/dataset \
    --workers 1 4 \
    --repeats 5 \
    --config ./images-extract.toml \
    --recipe transback \
    --json /tmp/images-extract-benchmark.json
```

`--output-root` behält die erzeugten Runs für eine manuelle Prüfung. Ohne diese
Option verwendet das Werkzeug ein temporäres Verzeichnis und entfernt nur seine
eigenen Benchmark-Ausgaben nach Abschluss.

Der Benchmark startet für jede Wiederholung einen vollständigen
`images-extract run` mit einer eindeutigen Ausgabe und `--workers N`. Es gibt
keine fest codierte Zeitgrenze und keinen automatischen „schneller/langsamer“-Fehler.
Ein nicht erfolgreicher Pipeline-Exitcode macht dagegen die betreffende Messung
ungültig und führt zu einem Fehlerstatus des Benchmarkprogramms.

## Erfasste Daten

Die JSON-Datei enthält:

- Schema-Version und UTC-Zeitpunkt,
- Git-Commit, Plattform, Python-Version und relevante Paketversionen,
- Anzahl, Gesamtgröße und Megapixel der lesbaren Eingabebilder,
- verwendeten CLI-Aufruf ohne Geheimnisse,
- einzelne Laufzeiten und Exitcodes,
- Median, p95, Bilder pro Sekunde und Megapixel pro Sekunde je Workerzahl,
- Anzahl und Größe erzeugter PNG-Dateien.

Fehlerausgaben werden begrenzt in das Ergebnis aufgenommen. Konfigurationen oder
Umgebungsvariablen mit Zugangsdaten dürfen nicht in Benchmarkartefakte gelangen.

## Repräsentative Datensätze

Ein aussagekräftiger Vergleich sollte mit festem Seed mindestens diese Klassen
abdecken:

| Klasse | Umfang | Zweck |
| --- | ---: | --- |
| klein | 100 × 256×256 | schneller Entwicklungsvergleich |
| Standard | 100 × 1024×1024 | gemischte RGB-, RGBA- und Graustufendaten |
| groß | 20 × 4096×4096 | Speicher- und I/O-Verhalten |
| Sprites | mehrere Blätter mit vielen Konturen | Extraktion und Sortierung |

Der Generator beziehungsweise das Dataset muss Formate, Seed und Prüfsummen
dokumentieren. Große Benchmarks gehören nicht als Binärdaten in das Repository.

## Regeln für Parallelität

- Parallelisiert wird auf Dateiebene, nicht durch konkurrierendes Schreiben auf
  dasselbe Ziel.
- Worker erhalten Pfade und kompakte Metadaten statt serialisierter Bildarrays.
- Zielnamen und Kollisionen werden vor dem Start aufgelöst.
- OpenCV-interne Threads werden bei mehreren Prozess-Workern begrenzt.
- Höchstens die konfigurierte Workerzahl dekodiert gleichzeitig; noch wartende
  Einträge enthalten nur Pfade und kompakte Metadaten statt Bildarrays.
- Manifest und Ausgabeordnung bleiben deterministisch.

Eine mögliche Workerobergrenze berücksichtigt CPU-Anzahl, den konfigurierten
Wert `max_workers`, die absolute Grenze 32 und bei großen Bildern zusätzlich ein
Speicherbudget.

## Interpretation

Vergleiche ausschließlich Läufe auf demselben Rechner, mit identischem Dataset,
derselben Konfiguration und möglichst ruhigem System. Median und p95 sind
aussagekräftiger als ein einzelner Bestwert.

Als Untersuchungsziel ist auf einer echten Vierkernumgebung mindestens etwa der
1,5-fache Durchsatz gegenüber einem Worker sinnvoll. Dies ist ausdrücklich kein
portabler CI-Grenzwert: kleine Datensätze, I/O-Limits und OpenCV-interne
Parallelität können eine niedrigere Skalierung erklären.

## Wiederherstellungs-Messung vom 29. August 2026

Der erste reproduzierbare Funktionscheck wurde mit dem eingecheckten
`examples/input`-Bild auf Linux/x86_64, Python 3.11.2, Pillow 12.3.0, NumPy 2.4.6
und OpenCV headless 5.0.0.93 ausgeführt. Pro Workerzahl wurde bewusst nur ein
Lauf ohne Warm-up gemessen; diese Werte bestätigen das Benchmarkwerkzeug, sind
aber keine belastbare Performance-Baseline.

| Worker | Laufzeit | Bilder/s | Fehlgeschlagene Läufe |
| ---: | ---: | ---: | ---: |
| 1 | 0,245 s | 4,08 | 0 |
| 2 | 0,267 s | 3,75 | 0 |
| 4 | 0,247 s | 4,04 | 0 |

Der nur 0,098-Megapixel große Einbild-Datensatz ist erwartungsgemäß von
Prozessstart und I/O dominiert; zusätzliche Worker bringen hier keinen Vorteil.
Eine Aussage zur Skalierung erfordert den oben beschriebenen Standarddatensatz
mit mehreren Bildern und mindestens drei Wiederholungen.

## CI

Geteilte GitHub-Runner eignen sich nicht für harte Performance-Grenzen. Dort darf
ein kleiner Benchmark manuell oder zeitgesteuert laufen und sein JSON-Ergebnis
als informatives Artefakt veröffentlichen. Verbindliche Regressionserkennung
benötigt einen kontrollierten, dedizierten Runner und eine vorher dokumentierte
Baseline.
