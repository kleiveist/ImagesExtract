"""
FillColors.py – ersetzt definierte Farbpaare mit Toleranz.
Vorgaben stehen in settings.ini unter [swap].
Das Modul bearbeitet ausschließlich den Ordner 03-swapcolors.
Abhängigkeiten: utils.py (INI lesen) und logger.py (Logging).
"""
from pathlib import Path
import cv2
import numpy as np
from _utils import load_settings_ini
from _logger import log_message, shorten_path
# ----------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------
def hex_to_lab(hex_color: str) -> np.ndarray:
    bgr = hex_to_bgr(hex_color).reshape(1, 1, 3)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[0, 0]
    return lab.astype(np.float32)

def hex_to_bgr(hex_color: str) -> np.ndarray:
    """Konvertiert Hex-Farbcode (#RRGGBB) in BGR-Array."""
    hex_color = hex_color.lstrip("#")
    r, g, b = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
    return np.array([b, g, r], dtype=np.uint8)

def deltaE_ciede2000(lab_img: np.ndarray, lab_color: np.ndarray) -> np.ndarray:
    """Berechnet CIEDE2000 Delta E zwischen Lab-Bild und Lab-Farbe."""
    # Lab-Werte extrahieren
    L1, a1, b1 = cv2.split(lab_img)
    L2, a2, b2 = lab_color

    # Vereinfachte Delta E Berechnung (hier könnte ein vollständiger CIEDE2000 Algorithmus implementiert werden)
    # Für eine einfache Implementierung nutzen wir die euklidische Distanz
    dL = L1 - L2
    da = a1 - a2
    db = b1 - b2

    return np.sqrt(dL**2 + da**2 + db**2)
# ----------------------------------------------------------
# Kernfunktion: ein Bild bearbeiten
# ----------------------------------------------------------
def fill_colors_in_image(img_path: Path,
                         pairs_hex: list[tuple[str, str]],
                         delta_e_max: float) -> None:
    img_bgr = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img_bgr is None:
        log_message(f"Bild nicht lesbar: {shorten_path(str(img_path))}", level="error")
        return
    alpha = None
    if img_bgr.shape[2] == 4:
        alpha = img_bgr[:, :, 3:].copy()
        img_bgr = img_bgr[:, :, :3]
    img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    # Referenzfarben vorbereiten
    pairs_lab_bgr = [
        (hex_to_lab(src_hex), hex_to_bgr(dst_hex))
        for src_hex, dst_hex in pairs_hex
    ]
    for src_lab, dst_bgr in pairs_lab_bgr:
        # ΔE*2000 pro Pixel
        dE = deltaE_ciede2000(img_lab, src_lab)
        mask = dE <= delta_e_max
        img_bgr[mask] = dst_bgr
    if alpha is not None:
        img_out = cv2.merge([img_bgr, alpha])
    else:
        img_out = img_bgr
    # Immer überschreiben
    out_path = str(img_path)
    if not cv2.imwrite(out_path, img_out):
        log_message(f"Fehler beim Schreiben: {shorten_path(out_path)}", level="error")
    else:
        log_message(f"Farben ersetzt: {shorten_path(out_path)}", level="info")
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
    folder_name = "swapcolors"  # Standardwert
    if "Settings" in cfg:
        folder_name = cfg["Settings"].get("output_foldes_collation8", "swapcolors")

    # Zielordnername mit Präfix "03-"
    target_folder_name = f"03-{folder_name}"
    log_message(f"Suche nach Ordner: '{target_folder_name}'", level="info")

    # Prüfen, ob der übergebene Pfad selbst der Zielordner ist
    if root.name == target_folder_name:
        swap_dir = root
        log_message(f"Zielordner ist der Startordner: {swap_dir}", level="info")
    else:
        # Ordner im übergebenen Pfad suchen
        swap_dir = find_collation_folder(root, target_folder_name)
        if swap_dir is None:
            log_message(f"Ordner '{target_folder_name}' nicht gefunden – Modul beendet.", level="warning")
            log_message(f"Verfügbare Unterordner: {[d.name for d in root.iterdir() if d.is_dir()]}", level="info")
            return
        log_message(f"Zielordner gefunden: {swap_dir}", level="info")

    # Swap-Konfiguration laden
    swap_cfg = cfg["swap"] if "swap" in cfg else {}

    # Farbpaar-Liste aus INI
    pairs_hex = []
    idx = 1
    while f"src_color_{idx}" in swap_cfg:
        src_hex = swap_cfg[f"src_color_{idx}"]
        dst_hex = swap_cfg[f"dst_color_{idx}"]
        pairs_hex.append((src_hex, dst_hex))
        idx += 1
    cfg = load_settings_ini()
    swap_cfg = cfg["swap"]
    # Farbpaar-Liste aus INI
    pairs_hex = []
    idx = 1
    while f"src_color_{idx}" in swap_cfg:
        src_hex = swap_cfg[f"src_color_{idx}"]
        dst_hex = swap_cfg[f"dst_color_{idx}"]
        pairs_hex.append((src_hex, dst_hex))
        idx += 1
    tol = 5.0  # Standardwert
    if "tolerance" in swap_cfg:
        try:
            tol = float(swap_cfg["tolerance"])
        except (ValueError, TypeError):
            log_message("Ungültiger Wert für 'tolerance' in settings.ini - verwende Standard (5.0)", level="warning")

    for img_path in swap_dir.rglob("*"):
        if img_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
            fill_colors_in_image(img_path, pairs_hex, tol)
# ----------------------------------------------------------
# Stand-alone-Aufruf
# ----------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Aufruf: python FillColors.py <Datums- oder Zielordner>")
        sys.exit(1)
    run(Path(sys.argv[1]))
