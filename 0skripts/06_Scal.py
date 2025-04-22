import os
from PIL import Image
import shutil

from _logger import log_message, shorten_path
from _utils import load_settings_ini, find_latest_date_folder

# Default-Skalierungsoptionen, falls in der INI nichts definiert ist
default_scale_options = {
    25: (25, 25),
    50: (50, 50),
    70: (70, 70),
    80: (80, 80),
    # Weitere Skalierungsstufen können hier ergänzt werden.
}

def scale_image(file_path, scale, scale_factors, output_dir):
    """
    Skaliert das Bild basierend auf dem angegebenen Skalierungswert und den zugehörigen Faktoren.
    
    :param file_path: Pfad zum Originalbild.
    :param scale: Skalierungswert (z.B. 75).
    :param scale_factors: Tuple mit (x_scale, y_scale).
    :param output_dir: Zielordner, in dem das skalierte Bild abgelegt wird.
    """
    log_message(f"Starte Skalierung von {shorten_path(file_path)} mit scale={scale}", level="info")
    
    try:
        img = Image.open(file_path)
    except Exception as e:
        log_message(f"Fehler: Datei {shorten_path(file_path)} konnte nicht geladen werden: {str(e)}", level="error")
        return

    new_width = int(img.width * (scale_factors[0] / 100))
    new_height = int(img.height * (scale_factors[1] / 100))
    try:
        scaled_img = img.resize((new_width, new_height), Image.LANCZOS)
    except Exception as e:
        log_message(f"Fehler beim Skalieren von {shorten_path(file_path)}: {str(e)}", level="error")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    new_file_name = f"{base_name}_x{scale}{ext}"
    output_path = os.path.join(output_dir, new_file_name)
    
    try:
        scaled_img.save(output_path)
        log_message(f"Skaliertes Bild gespeichert: {shorten_path(output_path)}", level="info")
    except Exception as e:
        log_message(f"Fehler beim Speichern des Bildes {shorten_path(output_path)}: {str(e)}", level="error")

def main():
    # INI laden und Basisordner ermitteln
    config = load_settings_ini()
    base_dir = os.getcwd()
    latest_date_folder = find_latest_date_folder(base_dir)
    
    # Skalierungsgrenzen aus der INI lesen (Abschnitt [Scaling])
    max_upscale = config.getint("Scaling", "max_upscale", fallback=200)
    max_downscale = config.getint("Scaling", "max_downscale", fallback=25)
    log_message(f"Skalierungsgrenzen: max_upscale={max_upscale}, max_downscale={max_downscale}", level="info")
    
    # Skalierungsoptionen aus der INI lesen
    try:
        active_scales_str = config.get("Scaling", "active_scales", fallback="25,50,75,150")
        active_scales = [int(x.strip()) for x in active_scales_str.split(",") if x.strip().isdigit()]
    except Exception as e:
        log_message(f"Fehler beim Laden der aktiven Skalierungsstufen: {str(e)}", level="warning")
        active_scales = list(default_scale_options.keys())
    
    # Skalierungsoptionen aus der INI oder Standardwerte verwenden
    scale_options = {}
    if config.has_option("Scaling", "scale_options"):
        scale_options_str = config.get("Scaling", "scale_options", fallback="")
        if scale_options_str:
            try:
                # Erwartetes Format: "25:25,25;50:50,50;75:75,75;150:150,150"
                for item in scale_options_str.split(";"):
                    item = item.strip()
                    if not item:
                        continue
                    key_part, val_part = item.split(":")
                    key = int(key_part.strip())
                    val_tuple = tuple(int(x.strip()) for x in val_part.split(","))
                    scale_options[key] = val_tuple
            except Exception as e:
                log_message(f"Fehler beim Parsen von scale_options: {str(e)}", level="warning")
                scale_options = default_scale_options
        else:
            scale_options = default_scale_options
    else:
        scale_options = default_scale_options

    # Filtere nur Skalierungsstufen, die innerhalb der definierten Grenzen liegen
    active_scales = [s for s in active_scales if s >= max_downscale and s <= max_upscale]
    if not active_scales:
        log_message("Keine gültigen Skalierungsstufen innerhalb der definierten Grenzen gefunden. Beende das Programm.", level="warning")
        return
    
    # Ermitteln der Collation‑Ordner (output_foldes_collationX) aus [Settings]
    collation_folders = []
    for key in config.options("Settings"):
        if key.startswith("output_foldes_collation"):
            folder_name = config.get("Settings", key)
            target_folder_name = f"03-{folder_name}"
            coll_folder = os.path.join(latest_date_folder, target_folder_name)
            if os.path.exists(coll_folder) and os.path.isdir(coll_folder):
                log_message(f"Gefundener Collation-Ordner: {shorten_path(coll_folder)}", level="info")
                collation_folders.append(coll_folder)
            else:
                log_message(f"Collation-Ordner '{target_folder_name}' nicht gefunden in {shorten_path(latest_date_folder)}.", level="info")
    
    if not collation_folders:
        log_message("Keine gültigen Collation-Ordner gefunden. Beende das Programm.", level="error")
        return

    # Liste unterstützter Bildformate
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".tiff"]

    # Rekursive Suche in jedem Collation‑Ordner
    for coll_folder in collation_folders:
        log_message(f"Starte Skalierung in Ordner: {shorten_path(coll_folder)}", level="info")
        # Durchlaufe alle Unterordner rekursiv
        for root, dirs, files in os.walk(coll_folder):
            # Falls der aktuelle Ordner ein Ausgabeordner (z. B. "x25") ist, überspringen
            if os.path.basename(root) in [f"x{scale}" for scale in active_scales]:
                continue

            # Damit wir nicht in bereits erstellte Ausgabeordner (x{scale}) hineinlaufen,
            # entfernen wir diese aus der weiteren Suche.
            dirs[:] = [d for d in dirs if d not in [f"x{scale}" for scale in active_scales]]
            
            for file in files:
                if any(file.lower().endswith(ext) for ext in supported_extensions):
                    file_path = os.path.join(root, file)
                    # Für jeden Skalierungswert: Ausgabeordner im selben Verzeichnis (relativ zum Bild) anlegen
                    for scale in active_scales:
                        scale_output_dir = os.path.join(root, f"x{scale}")
                        os.makedirs(scale_output_dir, exist_ok=True)
                        log_message(f"Verarbeite Datei: {shorten_path(file_path)} für Skalierung {scale}x", level="info")
                        scale_image(file_path, scale, scale_options[scale], scale_output_dir)
    
    log_message("Skalierung abgeschlossen.", level="info")

if __name__ == "__main__":
    main()
