import os
import cv2
from PIL import Image
import shutil
from _logger import log_message, shorten_path
from _utils import load_settings_ini, find_latest_date_folder

# -------------------------------------------------------------------
# Hilfsfunktion: Sucht einen Collation-Ordner (z. B. "03-Whitepaper")
# -------------------------------------------------------------------
def find_collation_folder(date_folder, collation_name):
    """
    Sucht im date_folder nach einem Ordner mit dem Namen collation_name.
    """
    collation_folder = os.path.join(date_folder, collation_name)
    if os.path.exists(collation_folder) and os.path.isdir(collation_folder):
        log_message(f"Gefundener Collation-Ordner: {shorten_path(collation_folder)}", level="info")
        return collation_folder
    else:
        log_message(f"Collation-Ordner '{collation_name}' nicht gefunden in {shorten_path(date_folder)}.", level="info")
        return None

# -------------------------------------------------------------------
# Objektextraktion aus einem Bild – Graustufen-Version
# -------------------------------------------------------------------
def extract_objects_from_image(file_path, extract_size=10, base_collation=None):
    """
    Liest ein Bild (inklusive Alphakanal) ein, wandelt es zuerst in ein Graustufenbild um
    und extrahiert dann Objekte (basierend auf dem Alphakanal). Erfolgreich extrahierte
    Objekte werden als separate PNG-Dateien gespeichert. Nach erfolgreicher Extraktion
    wird die Originaldatei gelöscht.

    :param file_path: Pfad zum Originalbild.
    :param extract_size: Mindestgröße (in Pixeln) eines Objekts (aus der INI, Standard: 10).
    :param base_collation: Basisordner, in den normalerweise das Original verschoben würde.
    """
    log_message(f"Starte Verarbeitung von {file_path} mit extract_size={extract_size}", level="info")

    # Bild inklusive Alphakanal einlesen
    img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        log_message(f"Fehler: Datei {file_path} konnte nicht geladen werden.", level="error")
        return

    # Umwandlung in Graustufen (für die spätere Extraktion)
    try:
        gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    except Exception as e:
        log_message(f"Fehler bei der Umwandlung in Graustufen für {file_path}: {str(e)}", level="error")
        return

    # Überprüfen, ob ein Alphakanal vorhanden ist
    if img.shape[2] == 4:
        alpha_channel = img[:, :, 3]
    else:
        log_message(f"Das Bild {file_path} hat keinen Alphakanal.", level="warning")
        return

    # Binärisierung des Alphakanals und Suche der Konturen
    _, binary = cv2.threshold(alpha_channel, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_dir = os.path.dirname(file_path)
    extracted_count = 0

    for i, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)
        if w < extract_size or h < extract_size:
            continue
        # Auf Basis des Graustufenbildes den Bereich ausschneiden
        cropped_img = gray_img[y:y+h, x:x+w]
        # Ebenso den entsprechenden Bereich des Alphakanals
        alpha_cropped = alpha_channel[y:y+h, x:x+w]
        mask = cv2.threshold(alpha_cropped, 1, 255, cv2.THRESH_BINARY)[1]
        pil_img = Image.fromarray(cropped_img).convert("L")
        pil_img.putalpha(Image.fromarray(mask))

        output_path = os.path.join(output_dir, f"{i+1:02}_{base_name}.png")
        pil_img.save(output_path)
        extracted_count += 1
        log_message(f"Objekt {i+1} gespeichert: {output_path}", level="info")

    if extracted_count > 0:
        try:
            os.remove(file_path)
            log_message(f"{extracted_count} Objekte aus {file_path} wurden verarbeitet. Originaldatei wurde gelöscht.", level="info")
        except Exception as e:
            log_message(f"Fehler beim Löschen der Originaldatei {file_path}: {str(e)}", level="error")
    else:
        log_message(f"Keine Objekte aus {file_path} extrahiert. Originaldatei bleibt erhalten.", level="info")

# -------------------------------------------------------------------
# Hilfsfunktion: Sucht alle Bilddateien in einem Verzeichnis (inkl. Unterordner)
# -------------------------------------------------------------------
def find_all_images_in_directory(directory):
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".tiff"]
    image_files = []
    for root, _, files in os.walk(directory):
        for file_name in files:
            if any(file_name.lower().endswith(ext) for ext in supported_extensions):
                image_files.append(os.path.join(root, file_name))
    return image_files

# -------------------------------------------------------------------
# Hauptprogramm
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Basisverzeichnis und neuesten Datum-Ordner ermitteln
    base_dir = os.getcwd()
    latest_date_folder = find_latest_date_folder(base_dir)

    # Konfiguration laden (settings.ini)
    config = load_settings_ini()

    # Aus der INI: Mindestgröße für zu extrahierende Objekte
    try:
        extract_size = config.getint("Settings", "extractsize")
    except Exception:
        extract_size = 10
        log_message("Ungültiger Wert für Settings.extractsize, Standardwert 10 wird verwendet.", level="warning")

    # Aus der INI: Namen der Collation-Bereiche (Ordner)
    output_foldes_collation3 = config.get("Settings", "output_foldes_collation3", fallback="Whitepaper")
    target_collation_folder_name3 = f"03-{output_foldes_collation3}"
    collation_folder3 = find_collation_folder(latest_date_folder, target_collation_folder_name3)

    output_foldes_collation4 = config.get("Settings", "output_foldes_collation4", fallback="Enhancwhite")
    target_collation_folder_name4 = f"03-{output_foldes_collation4}"
    collation_folder4 = find_collation_folder(latest_date_folder, target_collation_folder_name4)

    output_foldes_collation7 = config.get("Settings", "output_foldes_collation7", fallback="Enhwhitclean")
    target_collation_folder_name7 = f"03-{output_foldes_collation7}"
    collation_folder7 = find_collation_folder(latest_date_folder, target_collation_folder_name7)

    # Für beide Collation-Bereiche (Whitepaper und Enhancwhite) werden die Bilder verarbeitet:
    for collation_folder in [collation_folder3, collation_folder4, collation_folder7]:
        if collation_folder:
            log_message(f"Starte Verarbeitung in Ordner: {shorten_path(collation_folder)}", level="info")
            image_files = find_all_images_in_directory(collation_folder)
            if not image_files:
                log_message(f"Keine Bilddateien in {shorten_path(collation_folder)} gefunden.", level="warning")
            else:
                for file_path in image_files:
                    log_message(f"Verarbeite Datei: {file_path}", level="info")
                    extract_objects_from_image(file_path, extract_size=extract_size, base_collation=collation_folder)

    log_message("Extraktion abgeschlossen.", level="info")
