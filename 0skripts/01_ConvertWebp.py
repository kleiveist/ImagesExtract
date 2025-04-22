import os
import configparser
import sys
import datetime
from PIL import Image
from _logger import log_message, log_separator, shorten_path, init_logger, ICON_SUCCESS, ICON_ERROR, ICON_WARN, ICON_DELETE, ICON_ARROW

# **1. LOAD SETTINGS.INI**
script_directory = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_directory, "settings.ini")

config = configparser.ConfigParser()
config.read(config_path)

output_format = config["Settings"]["output_format"]
supported_formats = [".webp", ".bmp", ".jpg", ".jpeg", ".png", ".tiff"]

# **2. CHECK HOW THE SCRIPT WAS STARTED**
if len(sys.argv) > 1:
    base_folder = sys.argv[1]
else:
    base_folder = os.getcwd()

# **CHECK IF FILES EXIST (BEFORE CREATING A FOLDER)**
files_to_convert = [
    file for file in os.listdir(base_folder)
    if os.path.splitext(file)[1].lower() in supported_formats
]

if not files_to_convert:
    log_message("No convertible files found. Script will exit.", level="warning")
    sys.exit(0)  # Exit script

# **INITIALIZE LOGGER**
init_logger(base_folder)
script_name = os.path.basename(__file__)  # Dynamically get the script's filename
log_message(f"{script_name} started with Input-Folder: {shorten_path(base_folder)}", level="info")

# **3. CREATE NEW DATE-NAMED FOLDER**
today_str = datetime.datetime.now().strftime("%y%m%d")
new_folder = os.path.join(base_folder, today_str)

counter = 1
while os.path.exists(new_folder):
    new_folder = os.path.join(base_folder, f"{today_str}_{counter:02d}")
    counter += 1

os.makedirs(new_folder)
log_message(f"New working folder: {shorten_path(new_folder)}", level="info")

# **4. AUTOMATICALLY SORT & MOVE FILES**
log_separator()
log_message("Sorting files:", level="info")

file_dict = {}

for file in files_to_convert:
    file_ext = os.path.splitext(file)[1].lower()
    target_folder = os.path.join(new_folder, f"01-{file_ext.strip('.')}")
    os.makedirs(target_folder, exist_ok=True)

    original_path = os.path.join(base_folder, file)
    new_path = os.path.join(target_folder, file)
    os.rename(original_path, new_path)

    if file_ext not in file_dict:
        file_dict[file_ext] = []
    file_dict[file_ext].append(new_path)

    log_message(f"  - {file} {ICON_ARROW} {shorten_path(target_folder)}", level="info")

# **5. CREATE OUTPUT FOLDER**
output_folder = os.path.join(new_folder, f"02-{output_format.strip('.')}")
os.makedirs(output_folder, exist_ok=True)

# **6. START CONVERSION**
log_separator()
log_message(f"Starting conversion to {output_format.upper()}", level="info")

for file_ext, files in file_dict.items():
    for file_path in files:
        file_name = os.path.basename(file_path)
        output_file = os.path.splitext(file_name)[0] + output_format
        output_path = os.path.join(output_folder, output_file)

        try:
            with Image.open(file_path) as img:
                img.save(output_path, output_format.strip(".").upper())
            log_message(f"  - {file_name} {ICON_ARROW} {output_file} {ICON_SUCCESS} Successfully ", level="info")
        except Exception as e:
            log_message(f"  - {file_name} {ICON_ERROR} Error: {e}", level="error")

log_separator()
log_message(f"All converted files have been saved in\n'{shorten_path(output_folder)}'.", level="info")