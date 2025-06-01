import os
import configparser
import numpy as np
import cv2
from PIL import Image, ImageEnhance
from pathlib import Path
from _logger import log_message, shorten_path  # Zentrale Logging-Funktion und Hilfsfunktion
from _utils import load_settings_ini, get_output_format, find_latest_date_folder

# -------------------------------------------------------------------
# Hilfsfunktion: Collation-Ordner suchen
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
# Hilfsfunktion: Alle Bilddateien in einem Verzeichnis (und Unterordnern) finden
# -------------------------------------------------------------------
def find_all_images_in_directory(directory):
    """
    Findet alle unterstützten Bilddateien in einem Verzeichnis und dessen Unterordnern.
    """
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".tiff"]
    image_files = []
    for root, _, files in os.walk(directory):
        for file_name in files:
            if any(file_name.lower().endswith(ext) for ext in supported_extensions):
                image_files.append(os.path.join(root, file_name))
    return image_files

# -------------------------------------------------------------------
# Funktion: Bild bereinigen – Hauptobjekt isolieren
# -------------------------------------------------------------------
def process_image(image_path, tolerance_lower, tolerance_upper):
    """
    Öffnet ein Bild, sucht per binärer Segmentierung (mittels cv2.inRange)
    das größte zusammenhängende Objekt (oder das Objekt am Seedpunkt in der Bildmitte)
    und entfernt alle Bereiche, die nicht zu diesem Objekt gehören (setzt sie transparent).

    :param image_path: Pfad zum zu verarbeitenden Bild.
    :param tolerance_lower: Untere Grenze der Intensitätswerte.
    :param tolerance_upper: Obere Grenze der Intensitätswerte.
    :return: Das bereinigte Bild (als BGRA), oder None bei Fehlern.
    """
    log_message(f"Verarbeite Bild: {shorten_path(image_path)}", level="info")
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        log_message(f"Fehler beim Laden des Bildes: {shorten_path(image_path)}", level="error")
        return None

    # Sicherstellen, dass ein Alpha-Kanal vorhanden ist
    if len(img.shape) == 2:
        img_color = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        alpha_channel = np.full(img.shape, 255, dtype=np.uint8)
        img = cv2.merge([img_color[:,:,0], img_color[:,:,1], img_color[:,:,2], alpha_channel])
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    # Falls bereits BGRA, keine Änderung nötig

    # Umrechnung in Graustufen (nur für BGR, ohne Alpha)
    bgr = img[:, :, :3]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Erzeuge eine binäre Maske mittels cv2.inRange mit den angegebenen Toleranzwerten
    mask = cv2.inRange(gray, tolerance_lower, tolerance_upper)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        log_message(f"Keine zusammenhängenden Objekte im Bild gefunden: {shorten_path(image_path)}", level="warning")
        return None

    # Ermittele den Seedpunkt (Mitte des Bildes) und bestimme, welchem Objekt dieser angehört.
    h, w = gray.shape
    center = (w // 2, h // 2)
    seed_label = labels[center[1], center[0]]
    if seed_label != 0:
        chosen_label = seed_label
    else:
        areas = stats[1:, cv2.CC_STAT_AREA]  # Hintergrund (Label 0) wird ignoriert
        if areas.size == 0:
            log_message(f"Keine gültigen Objekte gefunden im Bild: {shorten_path(image_path)}", level="warning")
            return None
        chosen_label = np.argmax(areas) + 1  # +1, da Hintergrund ausgeschlossen

    # Erzeuge eine Binärmaske, die genau das gewählte Objekt markiert
    component_mask = (labels == chosen_label).astype(np.uint8) * 255
    area = stats[chosen_label, cv2.CC_STAT_AREA]
    if area < extract_size:
        log_message(f"Extrahiertes Objekt zu klein ({area} Pixel): {shorten_path(image_path)}", level="warning")
        return None

    # Alle Bereiche außerhalb des Hauptobjekts werden entfernt (Alpha auf 0 setzen)
    remove_mask = cv2.bitwise_not(component_mask)
    img[:, :, 3] = np.where(remove_mask == 255, 0, img[:, :, 3])
    return img

# -------------------------------------------------------------------
# STARTRUTINE
# -------------------------------------------------------------------
if __name__ == "__main__":
    log_message("Starte Bildverarbeitung...", level="info")

    # Arbeitsverzeichnis: Verzeichnis, in dem das Skript ausgeführt wird
    base_dir = os.getcwd()

    # 1. Finde den neuesten Datum-Ordner
    latest_date_folder = find_latest_date_folder(base_dir)

    # 2. SETTINGS.INI laden
    config = load_settings_ini()
    log_message("Lade settings.ini", level="info")

    # 3. Ausgabeformat ermitteln
    output_format = get_output_format(config)  # z. B. ".png"
    if not output_format.startswith("."):
        output_format = "." + output_format
    output_format = output_format.lower()

    # -------------------------------------------------------------------
    # Hilfsfunktionen zum Auslesen von Integer- und Float-Werten aus der INI
    # -------------------------------------------------------------------
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

    # Werte für die Bildbearbeitung aus dem [CleanUp]-Abschnitt einlesen
    extract_size    = get_int("Settings", "extractsize", 10)
    tolerance_lower = get_int("CleanUp", "tolerance_lower", 100)
    tolerance_upper = get_int("CleanUp", "tolerance_upper", 150)

    # Definition der akzeptierten Schalterwerte
    valueOn = ["true", "1", "yes", "on"]
    valueOff = ["false", "0", "no", "off"]

    # -------------------------------------------------------------------
    # Ordnernamen aus dem [Settings]-Bereich auslesen
    # -------------------------------------------------------------------
    folders_to_process = {
        "Collation1": config.get("Settings", "output_foldes_collation1", fallback="TransBack"),
        "Collation2": config.get("Settings", "output_foldes_collation2", fallback="Enhancement"),
        "Collation3": config.get("Settings", "output_foldes_collation3", fallback="Whitepaper"),
        "Collation4": config.get("Settings", "output_foldes_collation4", fallback="Enhancwhite"),
        "Collation5": config.get("Settings", "output_foldes_collation5", fallback="Enhanclean"),
        "Collation6": config.get("Settings", "output_foldes_collation6", fallback="Transclean"),
        "Collation7": config.get("Settings", "output_foldes_collation7", fallback="Enhwhitclean"),
        "Collation8": config.get("Settings", "output_foldes_collation8", fallback="Swapcolors"),
        "Collation9": config.get("Settings", "output_foldes_collation9", fallback="Invert")
    }

# -------------------------------------------------------------------
    # Auswertung der Toggle-Flags aus dem [CleanUp]-Abschnitt für Collation1 bis Collation6
    # Hier wird für jeden Collation-Key aus der INI geprüft, ob die Verarbeitung aktiviert ist.
    # -------------------------------------------------------------------
    collation_flags = {}
    for n in range(1, 9):
        key = f"collation{n}"
        try:
            flag_value = config.get("CleanUp", key).strip().lower()
        except (configparser.NoOptionError, configparser.NoSectionError):
            flag_value = "true"  # Standardwert, falls nicht definiert
        collation_flags[f"Collation{n}"] = flag_value in valueOn
    # -------------------------------------------------------------------
    # Erstelle ein Dictionary mit den vollständigen Pfaden der zu verarbeitenden Collation-Ordner,
    # allerdings nur, wenn das jeweilige Toggle-Flag auf "on" steht.
    # -------------------------------------------------------------------
    collation_folders = {}
    for collation_key, folder_name in folders_to_process.items():
        if not collation_flags.get(collation_key, True):
            log_message(f"Verarbeitung für {collation_key} ({folder_name}) wurde deaktiviert.", level="info")
            continue

        # Überspringe Ordner, deren Name ein '+' enthält
        if '+' in folder_name:
            log_message(f"Überspringe Ordner 03-{folder_name} (Name enthält '+').", level="info")
            continue

        target_name = f"03-{folder_name}"
        folder_path = find_collation_folder(latest_date_folder, target_name)
        if folder_path:
            collation_folders[collation_key] = folder_path

    if not collation_folders:
        log_message("Alle Collation-Verarbeitungen wurden deaktiviert. Skript wird beendet.", level="info")

    # -------------------------------------------------------------------
    # Verarbeitung der Bilder in den gefundenen (aktivierten) Collation-Ordnern
    # -------------------------------------------------------------------
    for folder_key, folder_path in collation_folders.items():
        log_message(f"Verarbeite Ordner: {shorten_path(folder_path)}", level="info")
        image_files = find_all_images_in_directory(folder_path)
        for image_file in image_files:
            processed_img = process_image(image_file, tolerance_lower, tolerance_upper)
            if processed_img is not None:
                if cv2.imwrite(image_file, processed_img):
                    log_message(f"Überschrieben: {shorten_path(image_file)}", level="info")
                else:
                    log_message(f"Fehler beim Überschreiben von: {shorten_path(image_file)}", level="error")
