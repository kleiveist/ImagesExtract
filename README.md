# ImagesExtract – Modular Batch-Image Processing Toolbox

> **A flexible, script-based pipeline for converting, organising, enhancing and exporting large numbers of raster images.**

![MIT License](https://img.shields.io/badge/license-MIT-green.svg)  ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)  ![Build](https://img.shields.io/badge/build-passing-success)

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Features](#features)
3. [Folder & Module Structure](#folder--module-structure)
4. [Quick Start](#quick-start)
5. [Configuration – `settings.ini`](#configuration)
6. [Detailed Workflow](#detailed-workflow)
7. [Command-Line Usage](#command-line-usage)
8. [Logging](#logging)
9. [Troubleshooting & FAQ](#troubleshooting--faq)
10. [Contributing](#contributing)
11. [License](#license)

---

## Project Overview
**ImagesExtract** is a collection of loosely coupled Python scripts designed to automate typical pre- and post-production image tasks:

* **Import & conversion** of _webp/jpg/jpeg/bmp/tiff_ (and many other formats) into a unified output format (default **PNG**)  
* **Folder hygiene & naming conventions** that keep all artefacts per date, format and processing stage nicely separated  
* **Transparent-background creation**, **object extraction**, **paper-style enhancement**, **cleanup**, **colour swapping**, **invert**, **scaling** and final **collation** – all driven by a single `settings.ini` file  
* Built-in **logging** with separate `log.txt` and `error_log.txt`  
* **Modular** – run the full pipeline or execute each module stand-alone  

The toolbox was developed to batch-process thousands of icons and product shots for e-commerce catalogues but works just as well for comics, stickers, UX assets or any other raster imagery.

---

## Features
| Stage | Script | Purpose |
|-------|--------|---------|
| **1 – Convert** | `ConvertWebp.py` | Converts mixed source formats into the unified output format and creates a fresh **date-stamped working folder** (e.g. `250601/`). |
| **2 – Organise** | `Folders.py` | Builds a canonical folder tree – converts are moved to `01-*`, converted assets to `02-png`, and additional **collation folders** (`03-TransBack`, `03-Enhancement`, …) are generated. |
| **3 – Transparency** | `TransBack.py` | Removes solid backgrounds or noise and adds an alpha channel based on Canny edge detection plus custom dark-threshold logic. |
| **4 – Extraction** | `Extract.py`, `ExtractGray.py` | Splits multi-icon spritesheets into individual files using alpha masks; `ExtractGray.py` offers a grey-scale variant. |
| **5 – Enhancement** | `Enhancement.py` | Applies a user-tunable water-colour/paper effect: colour quantisation, bilateral abstraction, edge overlay, contrast/brightness, noise. |
| **6 – Cleanup** | `CleanUp.py` | Isolates the main object (largest connected component) and clears everything else for razor-sharp transparency. |
| **7 – Colour Tools** | `SwapColors.py`, `invert.py` | Swap arbitrary HEX colour pairs within tolerance or fully invert colours (useful for dark mode assets). |
| **8 – Scaling** | `Scal.py` | Exports common pixel-multiples (25 %, 50 %, 70 %, 80 % …) into sibling `x25/`, `x50/` folders – values are 100 % INI-driven. |
| **9 – Collation** | `Collation.py` | Collects finished PNGs from all processing branches into convenient `+Collation` folders ready for hand-off. |
| **10 – Master Runner** | `startskript.py` | Recursively locates the **`Skripts/`** folder, reads module toggles from [Moduls] and executes everything in the correct order. |

---

## Folder & Module Structure
```
ImagesExtract/
├─ Skripts/
│  ├─ startskript.py
│  ├─ _logger.py
│  ├─ _utils.py
│  ├─ settings.ini
│  ├─ ConvertWebp.py
│  ├─ Folders.py
│  ├─ TransBack.py
│  ├─ Extract.py
│  ├─ ExtractGray.py
│  ├─ Enhancement.py
│  ├─ CleanUp.py
│  ├─ SwapColors.py
│  ├─ invert.py
│  ├─ Scal.py
│  └─ Collation.py
└─ <your-source-images>/
```
> **Tip:** Keep `Skripts/` version-controlled while placing your raw input images **outside** the repo.

---

## Quick Start
```bash
# 1.  Clone & enter the repo
$ git clone https://github.com/your-org/ImagesExtract.git
$ cd ImagesExtract/Skripts

# 2.  Create & activate a virtual env (recommended)
$ python -m venv .venv
$ source .venv/bin/activate  # Windows: .venv\Scripts\activate.bat

# 3.  Install dependencies
$ pip install -r requirements.txt  # see below

# 4.  Drop a bunch of images next to Skripts/ (or pass a path)
$ cp ../my_icons/*.webp ../

# 5.  Fire the whole pipeline
$ python startskript.py            # defaults to current working dir
#    or
$ python startskript.py /path/to/input_images
```
All generated artefacts reside in a **YYMMDD/** folder (e.g. `250601/`) created beside your sources.

### Requirements
* Python ≥ 3.10  
* [Pillow](https://pillow.readthedocs.io/)  
* [OpenCV-Python](https://pypi.org/project/opencv-python/)  
* numpy  

Create a `requirements.txt` (or let `pip-tools` generate one):
```
numpy>=1.26
opencv-python>=4.11
Pillow>=10.0
``` 

---

## Configuration
All behaviour is steered via **`settings.ini`**.  Important sections:

| Section | Key | Description | Default |
|---------|-----|-------------|---------|
| `[Settings]` | `output_format` | Target extension for `ConvertWebp.py` & downstream modules | `.png` |
|  | `extractsize` | Minimum pixel width/height of objects to keep during extraction | `100` |
|  | `output_foldes_collation*` | Human-readable names of your processing branches (prefixed with `03-`) | see file |
| `[LOGGER]` | `console_output` | Echo all log lines to stdout | `true` |
| `[Moduls]` | `<script>.py` | `yes/no` to enable or skip modules globally | `yes` |
| `[swap]` | `src_color_1`, `dst_color_1`, `tolerance` | Configure HEX colour replacements | – |
| `[Scaling]` | `active_scales` | Comma-separated list of percentages | `25,50,70,80` |

> 🔧 **Hint:** Toggle modules safely – unused dependencies never load.

---

## Detailed Workflow
```text
          ┌──────────────┐   01-webp/png/...           
 Source →  │ConvertWebp   │──────────────┐              
 images    └──────────────┘              │              
          YYMMDD/                        ▼              
                        02-png/ (master originals)     
                                       │              
              ┌──────────Folders────────┴─┐            
              │ 03-TransBack             │            
              │ 03-Enhancement           │ . . .       
              └──────────────────────────┘            
                         │  (parallel branches)       
         ...TransBack…Extract…Enhance…Scale…Collate…  
```
Each branch is completely **self-contained**.  Intermediate steps always overwrite in-place to save storage, while original inputs are preserved in `02-png/`.

---

## Command-Line Usage
Run everything (default order):
```bash
python startskript.py [INPUT_DIR]
```
Run a single module (for experimentation or CI):
```bash
python TransBack.py              # uses CWD & settings.ini
python Scal.py /path/to/250601   # explicit date folder
```
Arguments vary by script – open any `*.py` and read the docstring or `--help` block.

---

## Logging
* **`log.txt`** – full pipeline chronology (only if `[LOGGER] logging_enabled = true`)  
* **`error_log.txt`** – warnings, errors & deletions **always** collected  
* Each line is prefixed with intuitive icons: `[OK]`, `[ERROR]`, `[WARN]`, `[DELETE]`, `[INFO]`.

---

## Troubleshooting & FAQ
| Symptom | Probable Cause | Fix |
|---------|----------------|-----|
| `opencv-python` fails to import | Missing system libs on Linux | `sudo apt install libgl1` (Debian/Ubuntu) |
| `settings.ini not found` | Ran a module from the wrong directory | Always execute **inside** the `Skripts/` folder or supply `--ini /path` |
| No output images generated | `[Moduls] <script>.py = no` or wrong `output_format` | Enable the module / set correct extension |

Need more help? Open an [issue](https://github.com/your-org/ImagesExtract/issues) with logs attached.

---

## Contributing
1. Fork the repo & create your feature branch (`git checkout -b feat/awesome`)
2. Commit your changes with conventional commits
3. Push to the branch and open a PR

Please run `ruff` or `flake8`, add unit tests if possible and keep the coding style Pythonic & explicit.

---

## License
This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

---

> **ImagesExtract** – Because batch image processing should be transparent, reproducible and _fun_.
