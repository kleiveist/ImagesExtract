# ----------------------------------------------------------
# Einstellungsbereich mit Erklärungen
# ----------------------------------------------------------
# Stufenzahl                (color_levels):
#     Höhere Werte =       mehr Farben.
#     Niedrigere Werte =   stärkere Vereinfachung.
# ----------------------------------------------------------
# Abstraktionsgrad          (abstraction_degree):
#     Höhere Werte =       glattere und abstraktere Formen.
#     Niedrigere Werte =   mehr Details bleiben erhalten.
# ----------------------------------------------------------
# Umsetzungsgenauigkeit     (accuracy):
#     Höhere Werte =       weichere Kantenübergänge.
#     Niedrigere Werte =   schärfere Kanten.
# ----------------------------------------------------------
# Rauschintensität          (noise_intensity):
#     Höhere Werte =       stärkeres Papierkorn.
#     Niedrigere Werte =   subtileres Rauschen.
# ----------------------------------------------------------
# Gewichtung der Kantenüberlagerung (edge_weight):
#     Höhere Werte =       stärkere Kantenhervorhebung.
#     Niedrigere Werte =   weniger Kanten.
# ----------------------------------------------------------
# Kontrasterhöhung          (contrast):
#     Höhere Werte =       mehr Kontrast.
#     Niedrigere Werte =   weniger Kontrast.
# ----------------------------------------------------------
# Helligkeitserhöhung       (brightness):
#     Höhere Werte =       helleres Bild.
#     Niedrigere Werte =   dunkleres Bild.
# ----------------------------------------------------------
import os
import configparser
import numpy as np
import cv2
from PIL import Image, ImageEnhance
from pathlib import Path
from _logger import log_message, shorten_path  # Zentrale Logging-Funktion und Hilfsfunktion
from _utils import load_settings_ini, get_output_format, find_latest_date_folder

# -------------------------------------------------------------------
# Benutzerdefinierter Filter (ersetzt den alten dark_threshold-Ansatz)
# -------------------------------------------------------------------
def apply_custom_filter(image_path):
    """Wendet den benutzerdefinierten Filter auf ein Bild an."""
    # Bild mit OpenCV laden
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Bild konnte nicht geladen werden.")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Farbquantisierung (Color Clustering) mittels K-Means
    Z = img.reshape((-1, 3))
    Z = np.float32(Z)
    K = SETTINGS["color_levels"]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    attempts = 10
    _, labels, centers = cv2.kmeans(Z, K, None, criteria, attempts, cv2.KMEANS_RANDOM_CENTERS)
    centers = np.uint8(centers)
    quantized = centers[labels.flatten()]
    quantized = quantized.reshape(img.shape)

    # Erhöhe den Abstraktionsgrad durch mehrfache bilaterale Filterung
    for _ in range(SETTINGS["abstraction_degree"]):
        quantized = cv2.bilateralFilter(quantized, d=9, sigmaColor=75, sigmaSpace=75)

    # Kanten erkennen; hier wird "accuracy" zur Anpassung der Schwellwerte genutzt
    threshold1 = max(1, int(50 // SETTINGS["accuracy"]))
    threshold2 = max(1, int(150 // SETTINGS["accuracy"]))
    edges = cv2.Canny(quantized, threshold1=threshold1, threshold2=threshold2)
    # Kanten invertieren und in den Farbraum konvertieren
    edges_colored = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
    edges_inverted = cv2.bitwise_not(edges_colored)

    # Kombiniere das quantisierte Bild mit den invertierten Kanten,
    # wobei "edge_weight" das Mischungsverhältnis bestimmt
    combined = cv2.addWeighted(quantized, 1 - SETTINGS["edge_weight"],
                               edges_inverted, SETTINGS["edge_weight"], 0)

    # Subtiles Rauschen (Papierkorn) hinzufügen
    noise = np.random.normal(0, SETTINGS["noise_intensity"], combined.shape).astype(np.uint8)
    textured = cv2.addWeighted(combined, 0.95, noise, 0.05, 0)

    # Konvertiere zurück zu PIL
    final_image = Image.fromarray(textured)

    # Helligkeit und Kontrast feinjustieren
    enhancer = ImageEnhance.Contrast(final_image)
    final_image = enhancer.enhance(SETTINGS["contrast"])
    enhancer = ImageEnhance.Brightness(final_image)
    final_image = enhancer.enhance(SETTINGS["brightness"])

    return final_image

# -------------------------------------------------------------------
# Hilfsfunktion: Collation-Ordner suchen (keine Error-Ausgabe, nur Info)
# -------------------------------------------------------------------
def find_collation_folder(date_folder, collation_name):
    """
    Sucht innerhalb des date_folder nach einem Ordner mit dem Namen "03-[Collation-Name]".
    Wird der Ordner gefunden, so wird er zurückgegeben, ansonsten wird nur eine Info-Meldung ausgegeben.
    """
    collation_folder = os.path.join(date_folder, collation_name)
    if os.path.exists(collation_folder) and os.path.isdir(collation_folder):
        log_message(f"Gefundener Collation-Ordner: {shorten_path(collation_folder)}", level="info")
        return collation_folder
    else:
        log_message(f"Collation-Ordner '{collation_name}' nicht gefunden in {shorten_path(date_folder)}.", level="info")
        return None

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
output_format = get_output_format(config)  # z. B. ".png"
if not output_format.startswith("."):
    output_format = "." + output_format
output_format = output_format.lower()

# 4. Zusätzliche Bildverarbeitungs-Einstellungen aus der INI einlesen
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

# Bildverarbeitungsparameter für den benutzerdefinierten Filter
color_levels       = get_int("Settings", "color_levels", 7)         # Mehr Farben bei höheren Werten
abstraction_degree = get_int("Settings", "abstraction_degree", 2)   # Glattere Formen bei höheren Werten
accuracy           = get_int("Settings", "accuracy", 1)             # Weichere Kanten bei höheren Werten
noise_intensity    = get_int("Settings", "noise_intensity", 10)       # Intensität des Rauschens (Papierkorn)
edge_weight        = get_float("Settings", "edge_weight", 0.1)        # Gewichtung der Kantenüberlagerung
contrast           = get_float("Settings", "contrast", 1.2)           # Kontrasterhöhung
brightness         = get_float("Settings", "brightness", 1.05)        # Helligkeitserhöhung

# Setze die globalen Einstellungen, sodass sie in der Filterfunktion genutzt werden können.
SETTINGS = {
    "color_levels": color_levels,
    "abstraction_degree": abstraction_degree,
    "accuracy": accuracy,
    "noise_intensity": noise_intensity,
    "edge_weight": edge_weight,
    "contrast": contrast,
    "brightness": brightness
}

# 5. Output-Folder Collation aus settings.ini lesen
output_foldes_collation2 = config.get("Settings", "output_foldes_collation2", fallback="Enhancement")
target_collation_folder_name2 = f"03-{output_foldes_collation2}"

output_foldes_collation4 = config.get("Settings", "output_foldes_collation4", fallback="Enhancwhite")
target_collation_folder_name4 = f"03-{output_foldes_collation4}"

output_foldes_collation5 = config.get("Settings", "output_foldes_collation5", fallback="Enhanclean")
target_collation_folder_name5 = f"03-{output_foldes_collation5}"

output_foldes_collation7 = config.get("Settings", "output_foldes_collation7", fallback="Enhwhitclean")
target_collation_folder_name7 = f"03-{output_foldes_collation7}"

# 6. Finde die Collation-Ordner (in denen die Bilder ersetzt werden sollen)
collation_folder2 = find_collation_folder(latest_date_folder, target_collation_folder_name2)
collation_folder4 = find_collation_folder(latest_date_folder, target_collation_folder_name4)
collation_folder5 = find_collation_folder(latest_date_folder, target_collation_folder_name5)
collation_folder7 = find_collation_folder(latest_date_folder, target_collation_folder_name7)

# Nur existierende Ordner in die Liste aufnehmen
collation_folder_list = [folder for folder in [collation_folder2, collation_folder4, collation_folder5, collation_folder7] if folder is not None]

if not collation_folder_list:
    log_message("Keine gültigen Collation-Ordner gefunden. Skript wird beendet.", level="info")
    exit(0)
else:
    for folder in collation_folder_list:
        log_message(f"   {shorten_path(folder)}", level="info")

# 7. Ausgabe der Bildverarbeitungsparameter als Lognachrichten
log_message("\n==================== AKTUELLE EINSTELLUNGEN ====================", level="info")
log_message("Bildverarbeitungsparameter:", level="info")
log_message(f"  - Stufenzahl (color_levels): {color_levels}", level="info")
log_message(f"  - Abstraktionsgrad (abstraction_degree): {abstraction_degree}", level="info")
log_message(f"  - Umsetzungsgenauigkeit (accuracy): {accuracy}", level="info")
log_message(f"  - Rauschintensität (noise_intensity): {noise_intensity}", level="info")
log_message(f"  - Kantengewichtung (edge_weight): {edge_weight}", level="info")
log_message(f"  - Kontrasterhöhung (contrast): {contrast}", level="info")
log_message(f"  - Helligkeitserhöhung (brightness): {brightness}", level="info")
log_message("==============================================================\n", level="info")

# -------------------------------------------------------------------
# VERARBEITUNG DER BILDER
# -------------------------------------------------------------------
processed_files = 0

# Es werden ausschließlich Bilder innerhalb der gefundenen Collation-Ordner verarbeitet.
for current_folder in collation_folder_list:
    for root, dirs, files in os.walk(current_folder):
        for file in files:
            if file.lower().endswith(output_format):
                input_path = os.path.join(root, file)
                # Da die Bilder ersetzt werden, wird der Output-Pfad exakt derselbe sein wie der Input-Pfad.
                output_path = os.path.join(root, file)
                log_message(f"Verarbeite Datei: {file}", level="info")
                try:
                    final_image = apply_custom_filter(input_path)
                    final_image.save(output_path)
                    log_message(f"Erfolgreich verarbeitet: {file}", level="info")
                    processed_files += 1
                except Exception as e:
                    log_message(f"Fehler bei {file}: {str(e)}", level="error")

log_message(f"Verarbeitung abgeschlossen! {processed_files} Bilder verarbeitet.", level="info")
