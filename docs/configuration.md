# Konfigurationsreferenz

Neue Konfigurationen verwenden TOML. Eine vollständige Vorlage liegt in
[`images-extract.example.toml`](../images-extract.example.toml). Ohne `--config`
lädt ImagesExtract validierte eingebaute Standardwerte; eine angegebene Datei
muss auf `.toml` oder `.ini` enden. Unbekannte TOML-Schlüssel gelten als Fehler,
damit Tippfehler nicht unbemerkt das Verhalten ändern.

```text
images-extract run INPUT --output OUTPUT [--config FILE]
images-extract validate-config
images-extract validate-config --config FILE
```

CLI-Werte wie `--output`, `--workers`, `--recipe` und `--collision` haben für den
aktuellen Lauf Vorrang. Die vollständig aufgelöste Konfiguration wird im
Run-Manifest gespeichert.

## Vollständiges TOML-Beispiel

```toml
working_format = "png"
output_folder = "image_ext"
random_seed = 0
collision_strategy = "error"
max_workers = 32

[enhancement]
color_levels = 7
abstraction_passes = 2
accuracy = 1.0
noise_intensity = 10.0
edge_weight = 0.1
contrast = 1.2
brightness = 1.05
canny_low = 50
canny_high = 150

[transparency]
min_component_area = 100
kernel_size = 13
dilation_iterations = 1
dark_weight = 0.45
dark_threshold_offset = 45
canny_low = 32
canny_high = 155

[extraction]
min_width = 1
min_height = 1
min_area = 100
alpha_threshold = 1

[cleanup]
intensity_lower = 1
intensity_upper = 185
alpha_threshold = 1
min_area = 100
selection = "center_then_largest"

[scaling]
active_scales = [25, 50, 70, 80]
min_percent = 25
max_percent = 200

[scaling.scale_options]
"25" = [25, 25]
"50" = [50, 50]
"70" = [70, 70]
"80" = [80, 80]

[colors]
max_delta_e = 5.0
metric = "cie76"
overlap_policy = "first"
invert = false

[[colors.pairs]]
source = "#ffffff"
target = "#000000"

[logging]
file_enabled = false
console_enabled = true
directory = "_log"

[recipes.transback]
enabled = true
output_name = "TransBack"
steps = ["transparency", "extract"]

[recipes.enhancement]
enabled = false
output_name = "Enhancement"
steps = ["enhance", "transparency", "extract"]
```

Nicht angegebene Tabellen oder Werte behalten ihre Standardwerte.

## Allgemeine Werte

| Schlüssel | Standard | Vertrag |
| --- | --- | --- |
| `working_format` | `"png"` | derzeit ausschließlich `png` |
| `output_folder` | `"image_ext"` | sicherer relativer Pfad ohne `..` |
| `random_seed` | `0` | Ganzzahl von 0 bis 9.223.372.036.854.775.807 |
| `collision_strategy` | `"error"` | `error`, `suffix` oder `hash` |
| `max_workers` | `32` | Ganzzahl von 1 bis 32 |

Die CLI begrenzt `--workers N` zusätzlich auf
`1..min(max_workers, 32)`. `output_folder` ist für programmatisch abgeleitete
Standardausgaben verfügbar; beim CLI-Befehl `run` ist `--output` ausdrücklich
anzugeben.

## Enhancement

| Schlüssel | Standard | Gültiger Bereich |
| --- | ---: | --- |
| `color_levels` | 7 | Ganzzahl 1 bis 256 |
| `abstraction_passes` | 2 | Ganzzahl 0 bis 64 |
| `accuracy` | 1.0 | größer als 0 |
| `noise_intensity` | 10.0 | 0 bis 255 |
| `edge_weight` | 0.1 | 0 bis 1 |
| `contrast` | 1.2 | 0 bis 16 |
| `brightness` | 1.05 | 0 bis 16 |
| `canny_low` | 50 | Ganzzahl 0 bis 255 |
| `canny_high` | 150 | Ganzzahl 0 bis 255 |

`canny_low` darf `canny_high` nicht überschreiten. `random_seed` steuert sowohl
K-Means-Initialisierung als auch Rauschen, damit Wiederholungen reproduzierbar
bleiben.

## Transparenz

| Schlüssel | Standard | Gültiger Bereich |
| --- | ---: | --- |
| `min_component_area` | 100 | Ganzzahl ab 0 |
| `kernel_size` | 13 | Ganzzahl 1 bis 255 |
| `dilation_iterations` | 1 | Ganzzahl 0 bis 64 |
| `dark_weight` | 0.45 | 0 bis 1 |
| `dark_threshold_offset` | 45 | Ganzzahl −255 bis 255 |
| `canny_low` | 32 | Ganzzahl 0 bis 255 |
| `canny_high` | 155 | Ganzzahl 0 bis 255 |

Auch hier muss der untere Canny-Wert kleiner oder gleich dem oberen sein.

## Extraktion

| Schlüssel | Standard | Gültiger Bereich |
| --- | ---: | --- |
| `min_width` | 1 | positive Ganzzahl |
| `min_height` | 1 | positive Ganzzahl |
| `min_area` | 100 | positive Ganzzahl |
| `alpha_threshold` | 1 | Ganzzahl 0 bis 255 |

`extract_gray` verwendet dieselben Grenzwerte und versetzt die gemeinsame
Extraktionsstufe in den Graustufenmodus; der Name ist in Rezepten und über
`images-extract stage extract_gray` verfügbar.

## Cleanup

| Schlüssel | Standard | Gültiger Bereich |
| --- | ---: | --- |
| `intensity_lower` | 1 | Ganzzahl 0 bis 255 |
| `intensity_upper` | 185 | Ganzzahl 0 bis 255 |
| `alpha_threshold` | 1 | Ganzzahl 0 bis 255 |
| `min_area` | 100 | positive Ganzzahl |
| `selection` | `"center_then_largest"` | `center_then_largest`, `largest` oder `center` |

`intensity_lower` darf `intensity_upper` nicht überschreiten.

## Skalierung

`active_scales` enthält eindeutige positive Ganzzahlen innerhalb
`min_percent..max_percent`. Für jede aktive Skala muss ein Eintrag unter
`scaling.scale_options` existieren. Jeder Eintrag enthält genau zwei positive
Prozentwerte für X und Y.

```toml
[scaling]
active_scales = [50, 100]
min_percent = 25
max_percent = 200

[scaling.scale_options]
"50" = [50, 50]
"100" = [100, 100]
```

Verzeichnisse, deren Name vollständig `x` plus Ziffern entspricht, werden nie
erneut als Skalierungsquelle traversiert.

## Farben und Invertierung

Farbpaare verwenden `#RRGGBB`. `max_delta_e` ist nicht negativ; als Metrik ist
derzeit ausschließlich die euklidische LAB-Distanz `cie76` implementiert.

`overlap_policy` legt fest, was geschieht, wenn ein Pixel auf mehrere Quellfarben
passt:

- `first`: erstes passendes Paar gewinnt,
- `last`: letztes passendes Paar gewinnt,
- `error`: überlappende Regeln werden abgelehnt.

`invert = true` aktiviert die Invertierung über dieselbe Farbstufe. Zusätzliche
Paare werden als wiederholte `[[colors.pairs]]`-Tabellen notiert.

## Logging

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `file_enabled` | `false` | Laufprotokoll in eine Datei schreiben |
| `console_enabled` | `true` | Statusmeldungen auf der Konsole ausgeben |
| `directory` | `"_log"` | sicherer relativer Logpfad |

Zugangstoken, Dateiinhalte und andere Geheimnisse dürfen nie protokolliert oder
in das Manifest aufgenommen werden.

## Rezepte

Jedes Rezept besitzt:

- eine ID aus Kleinbuchstaben, Ziffern, `_` und `-`, beginnend mit einem
  Kleinbuchstaben,
- einen eindeutigen, sicheren `output_name`,
- mindestens einen Schritt ohne Duplikate,
- ein boolesches `enabled`.

Erlaubte interne Schritte sind `enhance`, `transparency`, `extract`,
`extract_gray`, `cleanup`, `colors` und `invert`. Mindestens ein Rezept muss
aktiviert sein.

| Eingebautes Rezept | Standard | Schritte |
| --- | --- | --- |
| `transback` | aktiv | `transparency`, `extract` |
| `enhancement` | inaktiv | `enhance`, `transparency`, `extract` |
| `whitepaper` | inaktiv | `transparency`, `extract_gray` |
| `enhancwhite` | inaktiv | `enhance`, `transparency`, `extract_gray` |
| `enhanclean` | inaktiv | `enhance`, `transparency`, `extract`, `cleanup` |
| `transclean` | inaktiv | `transparency`, `extract`, `cleanup` |
| `enhwhitclean` | inaktiv | `enhance`, `transparency`, `extract_gray`, `cleanup` |

Ein vorhandenes Rezept kann mit einer gleichnamigen TOML-Tabelle teilweise
überschrieben werden. Neue Rezept-IDs müssen ihre Schritte vollständig angeben.

## Legacy-`settings.ini`

Eine explizit mit `--config` angegebene `.ini`-Datei wird über den
Übergangsloader gelesen. Der Rest des Programms erhält trotzdem ausschließlich
das neue, validierte Konfigurationsmodell.

Unterstützte Zuordnungen umfassen:

| Legacy | Neues Modell |
| --- | --- |
| `[Settings] output_format` | `working_format` |
| `[Settings] extractsize` | Extraktions- und Cleanup-Mindestwerte |
| alte Enhancement-/TransBack-Werte | `[enhancement]` und `[transparency]` |
| `[Scaling]` | `[scaling]` und `[scaling.scale_options]` |
| `[CleanUp]` | `[cleanup]` und Rezeptschritte |
| `[swap] src_color_N/dst_color_N` | `[[colors.pairs]]` |
| `[LOGGER]` | `[logging]` |
| `[Moduls]` | aktivierte Schritte der betroffenen Rezepte |
| `output_foldes_collationN` | Rezeptname und `output_name` |
| `output_folders_collationN` | kompatible korrigierte Schreibweise |

Legacy-Boolesche Werte akzeptieren `true/false`, `1/0`, `yes/no` und `on/off`.
Ungültige Zahlen, unvollständige Farbpaare und unbekannte Collation-Indizes werden
als verständliche Config-Fehler gesammelt.

Der Legacy-Loader darf niemals `--move-sources`, `--overwrite` oder
`--delete-intermediates` aktivieren. Diese Optionen bleiben ausschließlich
bewusste Entscheidungen des aktuellen CLI-Aufrufs.

## Migrationsablauf

1. Bestehende INI unverändert über `--config /pfad/settings.ini` laden. Die
   eingecheckte Referenzdatei liegt unter `examples/legacy-settings.ini`.
2. Alle Validierungsfehler korrigieren, bevor Bilder verarbeitet werden.
3. Die aufgelöste Konfiguration im Manifest prüfen.
4. Relevante Werte in eine neue TOML-Datei übertragen.
5. TOML in einem kleinen, nicht-destruktiven Beispielrun gegen die INI-Ausgabe
   vergleichen.
