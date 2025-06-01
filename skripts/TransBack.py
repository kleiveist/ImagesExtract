#----------------------------------------------------------
# Logdatei aktivieren        (log_enabled):
#     True =               Logging wird aktiviert
#     False =              Logging wird deaktiviert
#----------------------------------------------------------
# Mindestobjektgröße        (tolerance):
#     Höhere Werte =       weniger kleine Objekte
#     Niedrigere Werte =   mehr Details erhalten
#     Empfohlener Bereich: 5-50
#----------------------------------------------------------
# Untere Canny-Schwelle     (canny_threshold1):
#     Niedrigere Werte =   mehr Kanten erkannt
#     Höhere Werte =       weniger Hintergrundrauschen
#     Empfohlener Bereich: 50-150
#----------------------------------------------------------
# Obere Canny-Schwelle      (canny_threshold2):
#     Höhere Werte =       weniger Kanten erkannt
#     Niedrigere Werte =   sensitivere Kantenerkennung
#     Empfohlener Bereich: 150-300
#----------------------------------------------------------
# Kernelgröße               (kernel_size):
#     Größere Werte =      stärkere Maskenausdehnung
#     Kleinere Werte =     präzisere Maskenbegrenzung
#     Empfohlener Bereich: 3-7
#----------------------------------------------------------
# Dilatations-Iterationen   (iterations):
#     Höhere Werte =       stärkere Maskenvergrößerung
#     Niedrigere Werte =   subtilere Anpassung
#     Empfohlener Bereich: 1-3
#----------------------------------------------------------
# Gewichtungsfaktor         (weight_factor):
#     Höhere Werte =       stärkere Dunkelpriorisierung
#     Niedrigere Werte =   ausgewogenere Schwellenwerte
#     Empfohlener Bereich: 0.7-0.9
#----------------------------------------------------------
# Schwellenoffset           (dark_threshold_offset):
#     Höhere Werte =       weniger dunkle Bereiche
#     Niedrigere Werte =   mehr dunkle Elemente
#     Empfohlene Anpassung: ±25
#----------------------------------------------------------
# Mindest-Icongröße         (min_icon_size):
#     Höhere Werte =       Filterung kleiner Objekte
#     Niedrigere Werte =   Beibehaltung kleiner Details
#     Empfohlener Bereich: 100-1000
#----------------------------------------------------------
# =====================================================================================
# KONFIGURATION
# =====================================================================================
#!/usr/bin/env python3
import os
import re
import configparser
import numpy as np
import cv2
from PIL import Image
from _logger import log_message, shorten_path  # Zentrale Logging-Funktion und Hilfsfunktion
from _utils import load_settings_ini, get_output_format, find_latest_date_folder

# -------------------------------------------------------------------
# Bildverarbeitungsfunktionen (Transparenter Hintergrund)
# -------------------------------------------------------------------
def calculate_dark_threshold(gray_image):
    """
    Berechnet den dynamischen Schwellenwert für dunkle Bereiche basierend auf
    weight_factor und dark_threshold_offset aus der INI.
    """
    min_b = np.min(gray_image)
    max_b = np.max(gray_image)
    calculated = min_b + weight_factor * (max_b - min_b)
    return int(calculated + dark_threshold_offset)

def process_image(img_path, output_path):
    """
    Verarbeitet ein einzelnes Bild:
      - Berechnet eine dunkle Bereichsmaske und ermittelt Kanten
      - Filtert Konturen, die kleiner als min_icon_size sind
      - Wendet die resultierende Maske an, sodass nicht erkannte Bereiche transparent werden
      - Speichert das Ergebnis als RGBA-Bild (überschreibt das Original im Zielordner)
    """
    try:
        with Image.open(img_path).convert("RGBA") as img:
            np_img = np.array(img)
            # Erzeuge ein Graustufenbild (RGB-Konvertierung notwendig für cv2)
            gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)

            # Dunkelbereichsmaskierung
            dark_threshold = calculate_dark_threshold(gray)
            _, dark_mask = cv2.threshold(gray, dark_threshold, 255, cv2.THRESH_BINARY_INV)

            # Kantenerkennung
            edges = cv2.Canny(gray, canny_threshold1, canny_threshold2)

            # Maskenoptimierung: Dilatation
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            edges_dilated = cv2.dilate(edges, kernel, iterations=iterations)

            # Kombinierte Maske aus dunkler Maske und Kanten
            combined_mask = cv2.bitwise_and(dark_mask, edges_dilated)
            contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            filtered_mask = np.zeros_like(combined_mask)
            for cnt in contours:
                if cv2.contourArea(cnt) > min_icon_size:
                    cv2.drawContours(filtered_mask, [cnt], -1, 255, thickness=cv2.FILLED)

            # Transparenz anwenden: Pixel außerhalb der Maske werden transparent
            np_img[filtered_mask == 0] = (0, 0, 0, 0)
            Image.fromarray(np_img, "RGBA").save(output_path)

            log_message(f"Erfolgreich verarbeitet: {os.path.basename(img_path)}", level="info")
            return True
    except Exception as e:
        log_message(f"Fehler bei {os.path.basename(img_path)}: {str(e)}", level="error")
        return False

# -------------------------------------------------------------------
# Hilfsfunktion: Collation-Ordner suchen
# -------------------------------------------------------------------
def find_collation_folder(date_folder, collation_name):
    """
    Sucht innerhalb des date_folder nach einem Ordner mit dem Namen, z. B.
    "03-TransBack" (bzw. dem jeweiligen Wert aus der settings.ini).
    Wird der Ordner gefunden, so wird er zurückgegeben, ansonsten wird das Skript beendet.
    """
    collation_folder = os.path.join(date_folder, collation_name)
    if os.path.exists(collation_folder) and os.path.isdir(collation_folder):
        log_message(f"Gefundener Collation-Ordner: {shorten_path(collation_folder)}", level="info")
        return collation_folder
    else:
        log_message(f"Collation-Ordner '{collation_name}' nicht gefunden in {shorten_path(date_folder)}. Skript wird beendet.", level="error")

# -------------------------------------------------------------------
# STARTRUTINE
# -------------------------------------------------------------------
log_message("Starte Bildverarbeitung...", level="info")

# Arbeitsverzeichnis (wo das Skript ausgeführt wird)
base_dir = os.getcwd()

# 1. Finde den neuesten Datum-Ordner (über _utils.py)
latest_date_folder = find_latest_date_folder(base_dir)

# 2. SETTINGS.INI laden (über _utils.py)
config = load_settings_ini()
log_message("Lade settings.ini", level="info")

# 3. Ausgabeformat ermitteln (über _utils.py)
output_format = get_output_format(config)  # z.B. ".png"
if not output_format.startswith("."):
    output_format = "." + output_format
output_format = output_format.lower()

# 4. Zusätzliche Bildverarbeitungs-Einstellungen aus der INI
def get_int(section, key, default):
    try:
        return config.getint(section, key)
    except (ValueError, KeyError):
        log_message(f"Ungültiger Wert für {section}.{key}, Standard ({default}) wird verwendet.", level="warning")
        return default

def get_float(section, key, default):
    try:
        return config.getfloat(section, key)
    except (ValueError, KeyError):
        log_message(f"Ungültiger Wert für {section}.{key}, Standard ({default}) wird verwendet.", level="warning")
        return default

# Die Parameter-Namen müssen mit deinen Einträgen in der settings.ini übereinstimmen
min_icon_size         = get_int("Settings", "min_icon_size", 100)
kernel_size           = get_int("Settings", "kernel_size", 12)
iterations            = get_int("Settings", "iterations", 1)
weight_factor         = get_float("Settings", "weight_factor", 0.45)
dark_threshold_offset = get_int("Settings", "dark_threshold_offset", 45)
canny_threshold1      = get_int("Settings", "canny_threshold1", 32)
canny_threshold2      = get_int("Settings", "canny_threshold2", 155)

# 5. Alle Output-Folder Collation-Einträge aus settings.ini sammeln
collation_folder_list = []
for key in config["Settings"]:
    if key.startswith("output_foldes_collation"):
        collation_value = config.get("Settings", key, fallback="TransBack")
        target_collation_folder_name = f"03-{collation_value}"
        folder = find_collation_folder(latest_date_folder, target_collation_folder_name)
        collation_folder_list.append(folder)

if not collation_folder_list:
    log_message("Keine Collation-Ordner in settings.ini gefunden. Skript wird beendet.", level="error")
    exit(1)

# 6. Ausgabe der aktuellen Einstellungen (optional)
log_message("\n==================== AKTUELLE EINSTELLUNGEN ====================", level="info")
log_message(f"Logging aktiviert: {config.getboolean('Settings', 'logging_enabled', fallback=True)}", level="info")
log_message(f"Ausgabeformat: {output_format}", level="info")
log_message(f"Mindestobjektgröße: {min_icon_size}px", level="info")
log_message(f"Kernelgröße: {kernel_size}", level="info")
log_message(f"Dilatations-Iterationen: {iterations}", level="info")
log_message(f"Gewichtungsfaktor: {weight_factor}", level="info")
log_message(f"Schwellenoffset: {dark_threshold_offset}", level="info")
log_message(f"Canny-Schwellenwerte: {canny_threshold1} - {canny_threshold2}", level="info")
log_message("Gefundene Collation-Ordner:", level="info")
for folder in collation_folder_list:
    log_message(f"   {shorten_path(folder)}", level="info")
log_message("==============================================================\n", level="info")

# -------------------------------------------------------------------
# VERARBEITUNG DER BILDER in allen Collation-Ordnern
# -------------------------------------------------------------------
total_processed = 0
for collation_folder in collation_folder_list:
    log_message(f"Verarbeite Bilder in Collation-Ordner: {shorten_path(collation_folder)}", level="info")
    for root, dirs, files in os.walk(collation_folder):
        for file in files:
            if file.lower().endswith(output_format):
                input_path = os.path.join(root, file)
                # Da wir die Bilder in den Collation-Ordnern bearbeiten wollen, wird das Bild an derselben Stelle überschrieben.
                output_path = os.path.join(root, file)
                log_message(f"Verarbeite Datei: {file}", level="info")
                if process_image(input_path, output_path):
                    total_processed += 1

log_message(f"Verarbeitung abgeschlossen! {total_processed} Bilder verarbeitet.", level="info")
