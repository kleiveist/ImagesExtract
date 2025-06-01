#!/usr/bin/env python3
import os
import re
import configparser
from _logger import log_message, shorten_path
from pathlib import Path

# ----------------------------------------------------------
# Einstellungen laden und verarbeiten (settings.ini)
# ----------------------------------------------------------

def load_settings_ini(ini_filename="settings.ini"):
    """
    Lädt die settings.ini aus dem gleichen Verzeichnis wie dieses Skript.
    Falls die INI-Datei nicht gefunden wird, wird das Skript beendet.
    """
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ini_filename)
    if not os.path.exists(config_path):
        log_message(f"settings.ini not found: {shorten_path(config_path)}", level="error")
        exit(1)
    config.read(config_path)
    log_message(f"settings.ini loaded: {shorten_path(config_path)}", level="info")
    return config

def get_output_format(config):
    """
    Liest aus der geladenen settings.ini das gewünschte Output-Format aus.
    Falls nicht gesetzt, wird '.png' als Standard verwendet.
    """
    output_format = config.get("Settings", "output_format", fallback=".png").lower().strip(".")
    log_message(f"Output format: {output_format}", level="info")
    return output_format

# ----------------------------------------------------------
# Suche nach dem neuesten Datum-Ordner
# ----------------------------------------------------------

def find_latest_date_folder(search_dir):
    """
    Sucht **innerhalb des in settings.ini definierten Sammelordners** nach Datumsordnern
    (JJMMTT oder JJMMTT_XX) und liefert den jüngsten zurück.

    Nutzt _logger.log_message und _logger.shorten_path zur Protokollierung.
    """
    cfg = load_settings_ini()
    collection_name = cfg.get("Settings", "output_folder", fallback="image_ext").strip()
    search_dir      = Path(search_dir) / collection_name     # <base>/<collection>
    if not search_dir.exists():
        log_message(f"Sammel-Ordner '{collection_name}' nicht gefunden – er wird angelegt.", level="info")
        search_dir.mkdir(parents=True, exist_ok=True)

    log_message(f"Searching for date folders in: {shorten_path(str(search_dir))}", level="info")

    try:
        entries = os.listdir(search_dir)
    except Exception as e:
        log_message(f"Could not read directory {search_dir}: {e}", level="error")
        exit(1)

    date_folders = sorted(
        [d for d in entries
         if os.path.isdir(os.path.join(search_dir, d)) and re.match(r"^\d{6}(_\d{2})?$", d)],
        reverse=True
    )

    log_message(f"Found date folders: {date_folders}", level="info")

    if not date_folders:
        log_message("No valid date folder (JJMMTT or JJMMTT_XX) found. Exiting.", level="error")
        exit(1)

    latest_folder = os.path.join(search_dir, date_folders[0])
    log_message(f"Selected latest date folder: {shorten_path(latest_folder)}", level="info")
    return latest_folder

# ----------------------------------------------------------
# Unterstützte Dateiformate
# ----------------------------------------------------------
supported_extensions = ['png', 'jpg', 'jpeg', 'bmp', 'tiff', 'webp']
