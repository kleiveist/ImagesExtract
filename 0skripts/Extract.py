import os
import configparser
import numpy as np
import cv2
from PIL import Image, ImageEnhance
from pathlib import Path
from _logger import log_message, shorten_path  # Zentrale Logging-Funktion und Hilfsfunktion
from _utils import load_settings_ini, get_output_format, find_latest_date_folder

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
output_format = get_output_format(config)  # z. B. ".png"
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

# Aus der INI: Mindestgröße der zu extrahierenden Objekte in Pixeln (extractsize)
extract_size = get_int("Settings", "extractsize", 10)

# 5. Output-Folder für die Verarbeitung aus settings.ini einlesen
#    Ordner 1: TransBack (für die Objektextraktion)
output_foldes_collation1 = config.get("Settings", "output_foldes_collation1", fallback="TransBack")
target_collation_folder_name1 = f"03-{output_foldes_collation1}"
collation_folder1 = find_collation_folder(latest_date_folder, target_collation_folder_name1)

#    Ordner 2: Enhancement
output_foldes_collation2 = config.get("Settings", "output_foldes_collation2", fallback="Enhancement")
target_collation_folder_name2 = f"03-{output_foldes_collation2}"
collation_folder2 = find_collation_folder(latest_date_folder, target_collation_folder_name2)

#    Ordner 5: Enhanclean
output_foldes_collation5 = config.get("Settings", "output_foldes_collation5", fallback="Enhanclean")
target_collation_folder_name5 = f"03-{output_foldes_collation5}"
collation_folder5 = find_collation_folder(latest_date_folder, target_collation_folder_name5)

#    Ordner 6: Transclean
output_foldes_collation6 = config.get("Settings", "output_foldes_collation6", fallback="Transclean")
target_collation_folder_name6 = f"03-{output_foldes_collation6}"
collation_folder6 = find_collation_folder(latest_date_folder, target_collation_folder_name6)

if not (collation_folder1 or collation_folder2 or collation_folder5 or collation_folder6):
    log_message("Kein gültiger Collation-Ordner gefunden. Skript wird beendet.", level="error")
    exit(0)

# -------------------------------------------------------------------
# Hilfsfunktion: Alle Bilddateien in einem Verzeichnis (und Unterordnern) finden
# -------------------------------------------------------------------
def find_all_images_in_directory(directory):
    """
    Findet alle unterstützten Bilddateien in einem Verzeichnis und dessen Unterordnern.
    :param directory: Wurzelverzeichnis.
    :return: Liste aller gefundenen Bilddateipfade.
    """
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".tiff"]
    image_files = []
    for root, _, files in os.walk(directory):
        for file_name in files:
            if any(file_name.lower().endswith(ext) for ext in supported_extensions):
                image_files.append(os.path.join(root, file_name))
    return image_files

# -------------------------------------------------------------------
# VERARBEITUNG DER BILDER – Objektextraktion (für beide Collation-Ordner)
# -------------------------------------------------------------------
def extract_objects_from_image(file_path, extract_size=10, base_folder=None):
    """
    Extrahiert einzelne Objekte aus einem Bild und speichert sie als separate PNG-Dateien.
    Nach erfolgreicher Extraktion wird die Originaldatei gelöscht.

    :param file_path: Pfad zum Originalbild.
    :param extract_size: Mindestgröße der Objekte in Pixeln.
    :param base_folder: Basisordner (z. B. TransBack oder Enhancement) – wird hier nicht mehr genutzt.
    """
    log_message(f"Starte Verarbeitung von {file_path} mit extract_size={extract_size}", level="info")

    # Datei einlesen (mit Alphakanal)
    img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        err_msg = f"Fehler: Datei {file_path} konnte nicht geladen werden."
        log_message(err_msg, level="error")
        return

    log_message("Datei erfolgreich geladen. Starte Verarbeitung...", level="info")

    # Überprüfen, ob ein Alphakanal vorhanden ist
    if img.shape[2] == 4:
        alpha_channel = img[:, :, 3]
    else:
        err_msg = f"Das Bild {file_path} hat keinen Alphakanal."
        log_message(err_msg, level="warning")
        return

    # Alphakanal binarisieren und Konturen finden
    _, binary = cv2.threshold(alpha_channel, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    extracted_count = 0

    for i, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)
        if w < extract_size or h < extract_size:
            continue
        cropped_img = img[y:y+h, x:x+w]
        alpha_cropped = alpha_channel[y:y+h, x:x+w]
        mask = cv2.threshold(alpha_cropped, 1, 255, cv2.THRESH_BINARY)[1]
        pil_img = Image.fromarray(cv2.cvtColor(cropped_img, cv2.COLOR_BGRA2RGBA))
        pil_img.putalpha(Image.fromarray(mask))

        output_path = os.path.join(os.path.dirname(file_path), f"{i+1:02}_{base_name}.png")
        pil_img.save(output_path)
        extracted_count += 1

        log_message(f"Objekt {i+1} gespeichert: {output_path}", level="info")

    if extracted_count > 0:
        try:
            os.remove(file_path)
            msg = f"{extracted_count} Objekte aus {file_path} wurden verarbeitet. Originaldatei wurde gelöscht."
            log_message(msg, level="info")
        except Exception as e:
            log_message(f"Fehler beim Löschen der Originaldatei {file_path}: {str(e)}", level="error")
    else:
        msg = f"Keine Objekte aus {file_path} extrahiert. Originaldatei bleibt erhalten."
        log_message(msg, level="info")

# -------------------------------------------------------------------
# Funktion für einen benutzerdefinierten Filter
# -------------------------------------------------------------------
def apply_custom_filter(input_path):
    """
    Platzhalter-Funktion für einen benutzerdefinierten Filter.
    Hier sollte die eigentliche Filterlogik implementiert werden.
    """
    try:
        image = Image.open(input_path)
    except Exception as e:
        log_message(f"Fehler beim Öffnen von {input_path}: {str(e)}", level="error")
        raise

    # Beispiel: Kontrast erhöhen (Anpassung nach Bedarf)
    # enhancer = ImageEnhance.Contrast(image)
    # image = enhancer.enhance(1.5)
    return image

# -------------------------------------------------------------------
# --- Hauptskript ---
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Zusammenstellung der Ordner, die verarbeitet werden sollen (sowohl TransBack als auch Enhancement)
    collation_folder_list = [folder for folder in [collation_folder1, collation_folder2, collation_folder5, collation_folder6] if folder is not None]

    # ---------------------------
    # 1. Objektextraktion in beiden Collation-Ordnern
    # ---------------------------
    for current_folder in collation_folder_list:
        image_files = find_all_images_in_directory(current_folder)
        if not image_files:
            log_message(f"Keine Bilddateien in {current_folder} gefunden.", level="warning")
        else:
            for file_path in image_files:
                log_message(f"Verarbeite Datei: {file_path}", level="info")
                # Übergabe des aktuellen Basisordners an die Funktion
                extract_objects_from_image(file_path, extract_size=extract_size, base_folder=current_folder)
            log_message(f"Extraktion abgeschlossen in {current_folder}.", level="info")

    # ---------------------------
    # 2. Anwendung des Custom-Filters
    #     Es werden Bilder in allen gefundenen Collation-Ordnern (TransBack und Enhancement)
    #     verarbeitet. Das gefilterte Bild wird als neue Datei (mit Präfix "filtered_") gespeichert,
    #     danach wird die Originaldatei gelöscht.
    # ---------------------------
    processed_files = 0

    for current_folder in collation_folder_list:
        for root, dirs, files in os.walk(current_folder):
            for file in files:
                if file.lower().endswith(output_format):
                    input_path = os.path.join(root, file)
                    output_path = os.path.join(root, "filtered_" + file)
                    log_message(f"Verarbeite Datei: {file}", level="info")
                    try:
                        final_image = apply_custom_filter(input_path)
                        final_image.save(output_path)
                        # Löschen der Originaldatei nach erfolgreicher Filterung
                        os.remove(input_path)
                        log_message(f"Erfolgreich verarbeitet: {file}. Originaldatei wurde gelöscht.", level="info")
                        processed_files += 1
                    except Exception as e:
                        log_message(f"Fehler bei {file}: {str(e)}", level="error")

    log_message(f"Verarbeitung abgeschlossen! {processed_files} Bilder verarbeitet.", level="info")
