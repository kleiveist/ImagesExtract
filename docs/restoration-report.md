# Wiederherstellungsbericht 2026-08-29

Dieser Bericht ordnet die umgesetzte Version `0.1.0` dem statischen Prüfbacklog
zu. Der unveränderte Ausgangsstand ist durch den annotierten Git-Tag
`legacy-baseline-2026-08-29` gesichert; die Wiederherstellung entstand auf
`restore/2026-08-29`.

## Abnahmestand

| Ticket | Status | Nachweis |
| --- | ---: | --- |
| P0-01 Legacy-Baseline | abgeschlossen | Repository reaktiviert, annotierter Tag und Wiederherstellungsbranch auf GitHub |
| P0-02 Installation | abgeschlossen | `pyproject.toml`, deklarierte Laufzeit-/Entwicklungsabhängigkeiten, erfolgreicher Sdist-/Wheel-Bau |
| P0-03 zentrale CLI | abgeschlossen | `images-extract run`, `stage`, `doctor`, `validate-config`; keine internen Python-Unterprozesse |
| P0-04 RunContext/Rezept-Graph | abgeschlossen | explizite Pfade, isolierte Run-ID, sieben zentral definierte Standardrezepte |
| P0-05 Preflight/Exitcodes | abgeschlossen | Validierung vor Run-Erzeugung, Exitcodes 0/1/2, `--allow-empty`, sichtbare Stufenfehler |
| P0-06 Dateisicherheit | abgeschlossen | Quellprüfsummen, atomare No-Clobber-Ausgabe, Symlink-/Race-Schutz, explizite destruktive Optionen |
| P0-07 PNG/RGBA-Vertrag | abgeschlossen | Mehrformat-Import, durchgängiges PNG/RGBA-Arbeits- und Endformat |
| P0-08 Extract/ExtractGray | abgeschlossen | Connected Components, räumliche Sortierung, echte Graustufe, keine automatische Löschung |
| P0-09 TransBack/Enhancement/Cleanup | abgeschlossen | validierte Parameter, fehlende Ergebnisse werden übersprungen, fester Seed, keine globalen Laufzeitwerte |
| P0-10 Scaling/Collation | abgeschlossen | vollständige Scale-Mappings, Ausschluss aller `xNN`-Quellordner, portable Kollisionsprüfung |
| P1-01 Config-Migration | abgeschlossen | striktes TOML-Schema und kompatibler Legacy-INI-Loader samt historischen Tippfehlern |
| P1-02 Colors/Invert | abgeschlossen | CIE76-Farbtausch und Invertierung als Standalone- sowie Rezeptschritte getestet |
| P1-03 Tests | abgeschlossen | 71 Tests für Formate, Pipeline, CLI, Sicherheit, Wiederholung und Fehlerpfade |
| P1-04 CI | abgeschlossen | Ruff, 80-%-Coverage-Grenze, Python 3.11–3.14, Wheel, Ubuntu/Fish und CachyOS/Fish |
| P1-05 Dokumentation/Hygiene | abgeschlossen | getesteter Quick Start, normale Markdown-Links, Logs/Caches/Legacy-Runner entfernt |
| P2-01 Performance | abgeschlossen | reproduzierbares Benchmarkwerkzeug, Workergrenze 32, Messung mit 1/2/4 Workern |

## Lokale Freigabeprüfung

| Prüfung | Ergebnis |
| --- | ---: |
| Ruff-Lint | bestanden |
| Ruff-Format | bestanden |
| pytest | 71 bestanden |
| Branch-Coverage | 81,75 %; Mindestgrenze 80 % |
| Sdist und Wheel | erfolgreich gebaut |
| Installation des Wheels in frischer Venv | erfolgreich; `pip check` ohne Konflikte |
| Wheel-CLI | Help, Doctor, Config-Validierung und Beispielrun erfolgreich |
| Standardpipeline | 3 Objekte, 12 Skalierungen, 15 finale Dateien |
| kompletter Rezept-Graph | 7 Rezepte, 105 finale Dateien, keine fehlgeschlagene Stufe |
| Determinismus | fachliche Endausgaben mit 1 und 2 Workern byteidentisch |
| leerer Input | Exitcode 1, kein neuer Run; mit `--allow-empty` Exitcode 0 |

## Sicherheitsvertrag

Standardläufe lesen Quellen ausschließlich. Vor und nach der Verarbeitung wird
jede Eingabe stabil gehasht; zusätzlich werden Größe, Inode, Gerät und
Änderungszeit verglichen. Zielnamen werden NFC-normalisiert und ohne Beachtung
der Groß-/Kleinschreibung vor dem ersten Schreiben geprüft. Temporäre Dateien
werden validiert und bei `overwrite = false` atomar ohne Überschreiben
veröffentlicht.

`--move-sources`, `--overwrite` und `--delete-intermediates` bleiben bewusste
Opt-ins. Der Move-Pfad erzeugt zuerst verifizierte Run-Kopien und kann bereits
entfernte Quellen aus lokalen Backups beziehungsweise den verifizierten Kopien
zurückrollen.

## Performance-Einordnung

Der Funktionsbenchmark mit dem kleinen Beispielbild endete für 1, 2 und 4 Worker
fehlerfrei. Wegen nur eines 0,098-Megapixel-Bildes dominieren Prozessstart und
I/O; die gemessenen 0,245 bis 0,267 Sekunden erlauben keine Aussage über
Parallel-Skalierung. Für belastbare Optimierungen bleibt ein größerer,
prüfsummengesicherter Referenzdatensatz erforderlich.

Die genauen Benchmarkregeln stehen in [performance.md](performance.md), das
Manifest- und Sicherheitsmodell in [architecture.md](architecture.md).
