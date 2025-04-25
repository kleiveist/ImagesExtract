"""
SwapColors.py – tauscht definierte Farbpaare mit Toleranz.
Vorgaben stehen in settings.ini unter [swap].
Das Modul bearbeitet ausschließlich den Ordner 03-swapcolors.
Abhängigkeiten: _utils.py (INI lesen) und _logger.py (Logging).
"""

from pathlib import Path
import cv2
import numpy as np

from _utils import load_settings_ini
from _logger import log_message, shorten_path


# ----------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------
def _hex_to_lab(hex_color: str) -> np.ndarray:
    bgr = _hex_to_bgr(hex_color).reshape(1, 1, 3)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[0, 0]
    return lab.astype(np.float32)


# ----------------------------------------------------------
# Kernfunktion: ein Bild bearbeiten
# ----------------------------------------------------------
def swap_colors_in_image(img_path: Path,
                         pairs_hex: list[tuple[str, str]],
                         delta_e_max: float,
                         overwrite: bool = True) -> None:
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
        (_hex_to_lab(src_hex), _hex_to_bgr(dst_hex))
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

    out_path = img_path if overwrite else img_path.with_stem(img_path.stem + "_swap")
    out_path = str(out_path)
    if not cv2.imwrite(out_path, img_out):
        log_message(f"Fehler beim Schreiben: {shorten_path(out_path)}", level="error")
    else:
        log_message(f"Farben getauscht: {shorten_path(out_path)}", level="info")
# ----------------------------------------------------------
# Einstieg (Collation-Controller oder CLI)
# ----------------------------------------------------------
def run(root: Path) -> None:
    """
    root:
      • direkt 03-swapcolors oder
      • ein Datumsordner wie 250425_01 (dann wird 03-swapcolors gesucht).
    """
    swap_dir = root
    if root.is_dir() and root.name != "03-swapcolors":
        cand = root / "03-swapcolors"
        if cand.is_dir():
            swap_dir = cand
        else:
            log_message("03-swapcolors nicht gefunden – Modul beendet.", level="warning")
            return

    cfg = load_settings_ini()
    swap_cfg = cfg["swap"]

    # Farbpaar-Liste aus INI
    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    idx = 1
    while f"src_color_{idx}" in swap_cfg:
        src = _hex_to_bgr(swap_cfg[f"src_color_{idx}"])
        dst = _hex_to_bgr(swap_cfg[f"dst_color_{idx}"])
        pairs.append((src, dst))
        idx += 1

    tol = swap_cfg.getfloat("tolerance", fallback=5.0)
    ow = swap_cfg.getboolean("overwrite", fallback=True)

    for img_path in swap_dir.rglob("*"):
        if img_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
            swap_colors_in_image(img_path, pairs, tol, overwrite=ow)


# ----------------------------------------------------------
# Stand-alone-Aufruf
# ----------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Aufruf: python SwapColors.py <Datums- oder swapcolors-Ordner>")
        sys.exit(1)
    run(Path(sys.argv[1]))
