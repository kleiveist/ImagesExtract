# Erwartungsvertrag der Beispielpipeline

Dieses Verzeichnis dokumentiert die fachlichen Erwartungen für
`examples/input`. Große, bei jedem Lauf neu erzeugte Ergebnisbäume werden nicht
eingecheckt.

Der Smoke-Test führt aus:

```bash
images-extract doctor
images-extract run examples/input --output /tmp/images-extract-example
```

Dabei gelten folgende Abnahmekriterien:

- Exitcode 0
- genau eine gefundene Eingabedatei mit SHA-256
  `42148ff234b5556ddd61fbfe57ea53e25e0c532acfb28c7e82cf9d75b9f0dc0a`
- unveränderte SHA-256-Prüfsummen aller Dateien unter `examples/input`
- genau ein neuer Run unter `/tmp/images-extract-example/runs`
- ein syntaktisch gültiges `manifest.json` mit `schema_version`
- Gesamtstatus `success`
- gültige PNG-/RGBA-Ausgaben
- keine temporären Dateien nach erfolgreichem Abschluss
- keine still überschriebenen Zielnamen

Mit der Standardkonfiguration enthält die fachliche Ausgabe drei räumlich
sortierte Objekte, vier Skalierungen pro Objekt und damit 15 Dateien unter
`collation/TransBack`. Arbeits- und Zwischenbilder werden bei der Zählung nicht
als finale Ausgaben betrachtet.

Ein zweiter Lauf mit denselben Eingaben muss einen eigenen Run erzeugen, ohne
verschachtelte `xNN`-Ordner oder mehrfach wiederholte Namenspräfixe. Die logisch
entsprechenden Ergebnisse müssen bei gleicher Konfiguration und gleichem Seed
identisch oder gemäß dem jeweiligen Bildtest toleranzgleich sein.

Ein anschließender Lauf mit einem leeren Eingabeordner muss mit Exitcode 1 enden,
keinen weiteren Run anlegen und die vorhandenen Run-Verzeichnisse bytegenau
unangetastet lassen. Mit `--allow-empty` ist stattdessen Exitcode 0 und ein
ausdrücklich übersprungener Status zulässig.

Pixelgenaue Referenzbilder werden nur ergänzt, wenn die jeweilige Operation über
alle unterstützten Python-, Pillow-, NumPy- und OpenCV-Versionen stabil ist.
Andernfalls prüfen Tests Bildmodus, Abmessungen, Alpha-Maske, Objektanzahl,
räumliche Reihenfolge und definierte numerische Toleranzen.
