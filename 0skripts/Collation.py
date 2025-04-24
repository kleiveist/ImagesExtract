import os
import shutil
import re
from _logger import log_message, shorten_path  # Zentrale Logging-Funktion und Hilfsfunktion
from _utils import load_settings_ini, find_latest_date_folder

def create_collation_folders():
    """
    Erstellt in allen definierten Output-Foldern (z. B. TransBack, Enhancement, Whitepaper, Enhancwhite, EierKucehn, ...)
    einen "+Collation"-Ordner und kopiert alle PNG-Dateien aus den jeweiligen Output-Foldern (und deren Unterordnern)
    dorthin.

    Dabei werden:
      - Dateien, die sich in Unterordnern befinden, deren Name exakt dem Muster "x" gefolgt von Ziffern entspricht
        (z. B. x25, x50, …), in einen entsprechenden Unterordner innerhalb von "+Collation" kopiert.
      - Liegen Dateien direkt im Output-Folder oder in Unterordnern ohne solches Muster, wird zusätzlich im Dateinamen
        nach einem Muster wie "_x25", "_x50", etc. gesucht. Trifft dieses zu, wird die Datei in einen entsprechenden
        Unterordner innerhalb von "+Collation" kopiert.
      - Alle übrigen PNG-Dateien werden direkt in den "+Collation"-Ordner kopiert.

    Wichtig: Es wird geprüft, ob mindestens ein Output-Folder (output_foldes_collationX) existiert. Falls nicht,
    wird ein Fehlerblock ausgegeben.
    """
    base_dir = os.getcwd()
    latest_date_folder = find_latest_date_folder(base_dir)
    config = load_settings_ini()

    # Definierte Output-Folder aus der settings.ini (Fallback-Werte, falls nicht definiert)
    folder_names = {
        "output_foldes_collation1": config.get("Settings", "output_foldes_collation1", fallback="TransBack"),
        "output_foldes_collation2": config.get("Settings", "output_foldes_collation2", fallback="Enhancement"),
        "output_foldes_collation3": config.get("Settings", "output_foldes_collation3", fallback="Whitepaper"),
        "output_foldes_collation4": config.get("Settings", "output_foldes_collation4", fallback="Enhancwhite"),
        "output_foldes_collation5": config.get("Settings", "output_foldes_collation5", fallback="Enhanclean"),
        "output_foldes_collation6": config.get("Settings", "output_foldes_collation6", fallback="Transclean"),
        "output_foldes_collation6": config.get("Settings", "output_foldes_collation6", fallback="Enhwhitclean"),
        # Hier können weitere Output-Folder ergänzt werden, z. B. "output_foldes_collation6": "Name6", etc.
    }

    # Erstelle Liste der vorhandenen Output-Folder (erwartet mit dem Präfix "03-")
    output_folders = []
    for key, folder in folder_names.items():
        folder_path = os.path.join(latest_date_folder, f"03-{folder}")
        if os.path.isdir(folder_path):
            output_folders.append(folder_path)
            log_message(f"Gefundener Output-Folder: {shorten_path(folder_path)}", level="info")
        else:
            log_message(f"Output-Folder {shorten_path(folder_path)} nicht gefunden.", level="warning")

    # Prüfe, ob mindestens ein Output-Folder existiert
    if not output_folders:
        log_message("Fehler: Kein gültiger Output-Folder gefunden. Mindestens ein Output-Folder (output_foldes_collationX) muss vorhanden sein.", level="error")
        # Hier kann alternativ auch eine Exception ausgelöst oder das Skript beendet werden:
        return

    # Bearbeitung jedes gefundenen Output-Folders
    for out_folder in output_folders:
        # Erstelle den +Collation-Ordner in diesem Output-Folder
        collation_dir = os.path.join(out_folder, "+Collation")
        os.makedirs(collation_dir, exist_ok=True)
        log_message(f"Verwende +Collation-Ordner: {shorten_path(collation_dir)}", level="info")

        # Rekursiver Durchlauf über out_folder (den +Collation-Ordner dabei überspringen)
        for root, dirs, files in os.walk(out_folder):
            if "+Collation" in dirs:
                dirs.remove("+Collation")
            for file in files:
                if file.lower().endswith(".png"):
                    file_path = os.path.join(root, file)
                    # Bestimme den relativen Pfad zum Output-Folder
                    rel_path = os.path.relpath(file_path, out_folder)
                    path_components = rel_path.split(os.sep)

                    target_subfolder = None
                    # 1. Prüfe, ob die Datei in einem Unterordner liegt, dessen Name exakt "x" gefolgt von Ziffern ist.
                    if len(path_components) > 1 and re.match(r'^x\d+$', path_components[0], re.IGNORECASE):
                        target_subfolder = path_components[0]
                    else:
                        # 2. Falls nicht, prüfe, ob der Dateiname (ohne Extension) ein Muster wie _x25, _x50, etc. enthält.
                        base_name = os.path.splitext(file)[0]
                        m = re.search(r'_x(\d+)$', base_name, re.IGNORECASE)
                        if m:
                            target_subfolder = "x" + m.group(1)

                    if target_subfolder:
                        target_subdir = os.path.join(collation_dir, target_subfolder)
                        os.makedirs(target_subdir, exist_ok=True)
                        target_file = os.path.join(target_subdir, file)
                        log_message(f"Kopiere {shorten_path(file_path)} in {shorten_path(target_subdir)}", level="info")
                    else:
                        target_file = os.path.join(collation_dir, file)
                        log_message(f"Kopiere {shorten_path(file_path)} in {shorten_path(collation_dir)}", level="info")
                    try:
                        shutil.copy2(file_path, target_file)
                    except Exception as e:
                        log_message(f"Fehler beim Kopieren von {shorten_path(file_path)} nach {shorten_path(target_file)}: {str(e)}", level="error")

if __name__ == "__main__":
    create_collation_folders()
