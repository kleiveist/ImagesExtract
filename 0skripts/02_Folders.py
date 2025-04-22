#!/usr/bin/env python3
import os
import shutil
import re
from _logger import (
    log_message,
    log_separator,
    log_sub_separator,
    shorten_path,
    init_logger,
    ICON_SUCCESS,
    ICON_ERROR,
    ICON_WARN,
    ICON_INFO
)
from _utils import load_settings_ini, get_output_format, find_latest_date_folder, supported_extensions

# Lade die Einstellungen über _utils.py
config = load_settings_ini()
output_format = get_output_format(config)

def find_existing_output_folder(parent_folder):
    """
    Sucht im übergebenen Ordner nach dem korrekten `02-[output_format]`-Ordner.
    Falls dieser nicht existiert, wird ein anderer Ordner, der mit "02-" beginnt, zurückgegeben.
    """
    preferred_folder = os.path.join(parent_folder, f"02-{output_format}")
    
    if os.path.exists(preferred_folder):
        return preferred_folder
    
    # Falls der bevorzugte Ordner nicht existiert, suche nach irgendeinem Ordner, der mit "02-" anfängt.
    for folder in os.listdir(parent_folder):
        folder_path = os.path.join(parent_folder, folder)
        if folder.startswith("02-") and os.path.isdir(folder_path):
            log_message(f"Preferred folder '{shorten_path(preferred_folder)}' not found. Using '{folder}' instead.", level="info")
            return folder_path
    return None

def process_existing_output_folder():
    """
    Verarbeitet den neuesten Datum-Ordner:
      1. Kopiert Bilder in individuelle Unterordner im '02-[output_format]'-Ordner (für Backup und weitere Verarbeitung).
      2. Kopiert die Bilder zusätzlich in alle '03-[output_foldes_collationX]'-Ordner, die in settings.ini definiert sind.
    
    Anschließend werden die Bilder aus den Unterordnern zurück in den '02-[output_format]'-Ordner verschoben
    und die leeren Unterordner gelöscht.
    """
    # Arbeitsverzeichnis (Skriptverzeichnis)
    script_dir = os.getcwd()
    # Logger initialisieren (setzt BASE_DIRECTORY für relative Pfadangaben)
    init_logger(script_dir)
    
    # Ermittle den neuesten Datum-Ordner (die _utils-Version liefert einen vollständigen Pfad)
    latest_date_folder = find_latest_date_folder(script_dir)
    if not latest_date_folder:
        return  # Kein gültiger Datum-Ordner gefunden
    
    # Da find_latest_date_folder bereits einen absoluten Pfad liefert, verwenden wir diesen direkt
    parent_folder = latest_date_folder
    
    # Finde den '02-[output_format]'-Ordner (oder einen alternativen Ordner)
    target_folder = find_existing_output_folder(parent_folder)
    if not target_folder:
        log_message(f"No `02-[format]` folder found in '{shorten_path(parent_folder)}'. Please run the conversion first.", level="error")
        return
    
    log_separator()
    log_message(f"Processing images in: {shorten_path(target_folder)}", level="info")
    
    # Ermittle in den Einstellungen alle Schlüssel, die mit "output_foldes_collation" beginnen
    collation_keys = [key for key in config["Settings"] if key.startswith("output_foldes_collation")]
    collation_keys.sort()  # z. B. 1, 2, 3, ...
    
    # Verarbeite alle Dateien im '02-[output_format]'-Ordner
    for filename in os.listdir(target_folder):
        file_path = os.path.join(target_folder, filename)
        # Überspringe Einträge, die keine Dateien sind (z. B. bereits erstellte Ordner)
        if not os.path.isfile(file_path):
            continue
        
        file_ext = os.path.splitext(filename)[1].lower().strip(".")
        if file_ext in supported_extensions:
            # Erstelle einen Unterordner basierend auf dem Bildnamen (ohne Endung)
            folder_name = os.path.splitext(filename)[0]
            image_folder_path = os.path.join(target_folder, folder_name)
            if not os.path.exists(image_folder_path):
                os.makedirs(image_folder_path)
                log_message(f"Created folder: {shorten_path(image_folder_path)}", level="info")
            
            # Kopiere das Bild in seinen Unterordner (das Original bleibt im '02'-Ordner)
            destination_file = os.path.join(image_folder_path, filename)
            try:
                shutil.copy2(file_path, destination_file)
                log_message(f"{filename} -> {shorten_path(image_folder_path)} {ICON_SUCCESS} Copied", level="info")
            except Exception as e:
                log_message(f"Copy operation failed: '{shorten_path(file_path)}' -> '{shorten_path(destination_file)}': {e}", level="error")
                continue
            log_sub_separator()
            
            # Kopiere das Bild in alle '03-[output_foldes_collationX]'-Ordner, die in settings.ini definiert sind
            for key in collation_keys:
                collation_value = config.get("Settings", key, fallback=None)
                if collation_value:
                    # Zielordner erhält das Präfix "03-"
                    collation_folder_name = f"03-{collation_value}"
                    collation_folder_path = os.path.join(parent_folder, collation_folder_name)
                    
                    # Erstelle den 03-Ordner, falls er nicht existiert
                    if not os.path.exists(collation_folder_path):
                        os.makedirs(collation_folder_path)
                        log_message(f"Created folder: {shorten_path(collation_folder_path)}", level="info")
                    
                    # Erstelle einen Unterordner für das Bild innerhalb des 03-Ordners
                    collation_image_subfolder = os.path.join(collation_folder_path, folder_name)
                    if not os.path.exists(collation_image_subfolder):
                        os.makedirs(collation_image_subfolder)
                        log_message(f"Created folder: {shorten_path(collation_image_subfolder)}", level="info")
                    
                    # Kopiere das Bild in den entsprechenden 03-Unterordner
                    collation_destination_file = os.path.join(collation_image_subfolder, filename)
                    try:
                        shutil.copy2(file_path, collation_destination_file)
                        log_message(f"{filename} -> {shorten_path(collation_image_subfolder)} {ICON_SUCCESS} Copied", level="info")
                    except Exception as e:
                        log_message(f"Copy operation failed: '{shorten_path(file_path)}' -> '{shorten_path(collation_destination_file)}': {e}", level="error")
                    log_sub_separator()
                    
    # Nachdem alle Bilder kopiert wurden, werden sie aus den Unterordnern zurück in den '02-[output_format]'-Ordner verschoben und die leeren Ordner gelöscht.
    log_separator()
    log_message("Moving images back to 02 folder & deleting subfolders", level="info")
    log_separator()
    for entry in os.listdir(target_folder):
        entry_path = os.path.join(target_folder, entry)
        if os.path.isdir(entry_path):
            # Verschiebe alle Dateien aus dem Unterordner in den übergeordneten '02'-Ordner
            for subfile in os.listdir(entry_path):
                subfile_path = os.path.join(entry_path, subfile)
                if os.path.isfile(subfile_path):
                    destination_path = os.path.join(target_folder, subfile)
                    try:
                        shutil.move(subfile_path, destination_path)
                        log_message(f"Moved {shorten_path(subfile_path)} -> {shorten_path(destination_path)}", level="info")
                    except Exception as e:
                        log_message(f"Error moving {shorten_path(subfile_path)}: {e}", level="error")
            # Lösche den nun leeren Unterordner
            try:
                os.rmdir(entry_path)
                log_message(f"Deleted folder: {shorten_path(entry_path)}", level="info")
            except Exception as e:
                log_message(f"Error deleting folder {shorten_path(entry_path)}: {e}", level="error")
    
    log_separator()

if __name__ == "__main__":
    process_existing_output_folder()
