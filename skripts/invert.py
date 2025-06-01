"""
Invert.py – kehrt die Farben in Bildern um.
Das Modul bearbeitet ausschließlich den Ordner 'invert'.
Abhängigkeiten: utils.py (INI lesen) und logger.py (Logging).
"""
from pathlib import Path
import cv2
import numpy as np
from _utils import load_settings_ini
from _logger import log_message, shorten_path

# ----------------------------------------------------------
# Kernfunktion: ein Bild bearbeiten
# ----------------------------------------------------------
def invert_colors_in_image(img_path: Path) -> None:
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        log_message(f"Bild nicht lesbar: {shorten_path(str(img_path))}", level="error")
        return

    alpha = None
    if img.shape[2] == 4:  # Bild hat einen Alpha-Kanal
        alpha = img[:, :, 3:].copy()
        img_color = img[:, :, :3]
    else:
        img_color = img

    # Farben invertieren
    inverted = 255 - img_color

    # Alpha-Kanal wieder hinzufügen, falls vorhanden
    if alpha is not None:
        img_out = cv2.merge([inverted, alpha])
    else:
        img_out = inverted

    # In Originaldatei speichern
    out_path = str(img_path)
    if not cv2.imwrite(out_path, img_out):
        log_message(f"Fehler beim Schreiben: {shorten_path(out_path)}", level="error")
    else:
        log_message(f"Farben invertiert: {shorten_path(out_path)}", level="info")

# ----------------------------------------------------------
# Hilfsfunktion zum Finden des Collation-Ordners
# ----------------------------------------------------------
def find_collation_folder(root_folder: Path, target_folder_name: str) -> Path:
    """Sucht den Collation-Ordner im angegebenen Pfad."""
    candidate = root_folder / target_folder_name
    if candidate.is_dir():
        return candidate
    return None

# ----------------------------------------------------------
# Einstieg (Collation-Controller oder CLI)
# ----------------------------------------------------------
def run(root: Path) -> None:
    """
    root:
      • direkt der Zielordner oder
      • ein Datumsordner (dann wird der konfigurierte Ordner gesucht).
    """
    # Einstellungen aus INI laden
    cfg = load_settings_ini()

    # Debug-Informationen
    log_message(f"Startordner: {root}", level="info")

    # Ordnernamen aus Settings lesen
    folder_name = "invert"  # Standardwert
    if "Settings" in cfg:
        folder_name = cfg["Settings"].get("output_foldes_collation9", "invert")

    # Zielordnername mit Präfix "03-"
    target_folder_name = f"03-{folder_name}"
    log_message(f"Suche nach Ordner: '{target_folder_name}'", level="info")

    # Prüfen, ob der übergebene Pfad selbst der Zielordner ist
    if root.name == target_folder_name:
        invert_dir = root
        log_message(f"Zielordner ist der Startordner: {invert_dir}", level="info")
    else:
        # Ordner im übergebenen Pfad suchen
        invert_dir = find_collation_folder(root, target_folder_name)
        if invert_dir is None:
            log_message(f"Ordner '{target_folder_name}' nicht gefunden – Modul beendet.", level="warning")
            log_message(f"Verfügbare Unterordner: {[d.name for d in root.iterdir() if d.is_dir()]}", level="info")
            return
        log_message(f"Zielordner gefunden: {invert_dir}", level="info")

    # Invert-Konfiguration laden (für zukünftige Erweiterungen)
    invert_cfg = cfg["invert"] if "invert" in cfg else {}

    # Alle Bilder im Ordner und Unterordnern verarbeiten
    processed_count = 0
    for img_path in invert_dir.rglob("*"):
        if img_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
            invert_colors_in_image(img_path)
            processed_count += 1

    log_message(f"Invert abgeschlossen: {processed_count} Bilder verarbeitet", level="info")
    log_separator()

# ----------------------------------------------------------
# Stand-alone-Aufruf
# ----------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Aufruf: python Invert.py <Datums- oder Zielordner>")
        sys.exit(1)
    run(Path(sys.argv[1]))
