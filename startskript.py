import os
import sys
import subprocess
import configparser

def find_0skripts_directory(start_path):
    """Suche rekursiv nach dem `0Skripts`-Ordner, indem nach oben gegangen wird."""
    current_path = start_path
    while True:
        possible_path = os.path.join(current_path, "Skripts")
        if os.path.exists(possible_path):
            return possible_path  # `Skripts` wurde gefunden!

        # Falls Root-Verzeichnis erreicht, abbrechen
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:
            return None  # `0Skripts` nicht gefunden
        current_path = parent_path  # Eine Ebene nach oben gehen

# **1. FINDING TEST SCRIPT DIRECTORY (CURRENT LOCATION)**
current_test_directory = os.getcwd()

# **2. FIND THE CENTRAL `0Skripts` DIRECTORY RECURSIVELY**
script_directory = find_0skripts_directory(current_test_directory)

# **3. CHECK IF `0Skripts` DIRECTORY EXISTS**
if not script_directory:
    print("Could not find `0Skripts` directory! Make sure it exists in a parent directory.")
    sys.exit(1)

# **4. ADD `0Skripts` TO PYTHON PATH**
sys.path.append(script_directory)

# **5. IMPORT LOGGER FROM `_logger.py`**
try:
    from _logger import log_message, log_separator, shorten_path_last_n, init_logger
except ImportError:
    print("Could not import logger. Make sure `_logger.py` is in `Skripts`.")
    sys.exit(1)

# **6. LOAD CONFIGURATION FROM .ini FILE**
# Es wird nun in 0Skripts nach der settings.ini gesucht
config = configparser.ConfigParser()
config_file = os.path.join(script_directory, "settings.ini")
if not os.path.exists(config_file):
    log_message("Configuration file 'settings.ini' not found in the 0Skripts directory.", level="error")
    sys.exit(1)
config.read(config_file)

# Definiere gültige Werte für aktiviert/deaktiviert
valueOn = ["true", "1", "yes", "on"]
valueOff = ["false", "0", "no", "off"]

# **7. DEFINE SCRIPT PATHS**
part_script1 = os.path.join(script_directory, "ConvertWebp.py")
part_script2 = os.path.join(script_directory, "Folders.py")
part_script3 = os.path.join(script_directory, "Enhancement.py")
part_script4 = os.path.join(script_directory, "TransBack.py")
part_script5 = os.path.join(script_directory, "Extract.py")
part_script6 = os.path.join(script_directory, "ExtractGray.py")
part_script7 = os.path.join(script_directory, "CleanUp.py")
part_script8 = os.path.join(script_directory, "Scal.py")
part_script9 = os.path.join(script_directory, "Collation.py")
#part_script10 = os.path.join(script_directory, "SwapColors.py") 
#part_script11 = os.path.join(script_directory, "invert.py")
# part_script12 = os.path.join(script_directory, "Modu12.py")

# **8. INITIALIZE LOGGER**
init_logger(current_test_directory)

log_separator()
log_message(f"Starting test script in: {shorten_path_last_n(current_test_directory, 2)}", level="info")

# **9. DEFINE SCRIPTS TO RUN WITH CONFIGURATION CHECK**
scripts_to_run = [
    ("ConvertWebp.py", part_script1),
    ("Folders.py", part_script2),
    ("Enhancement.py", part_script3),
    ("TransBack.py", part_script4),
    ("Extract.py", part_script5),
    ("ExtractGray.py", part_script6),
    ("CleanUp.py", part_script7),
    ("Scal.py", part_script8),
    ("Collation.py", part_script9)
#    ("SwapColors.py", part_script10),
#    ("invert.py", part_script11),
#    ("Modul6.py", part_script12)
]

for script_name, script_path in scripts_to_run:
    # Hole den Modul-Status aus der ini-Datei (Standard: aktiviert)
    enabled_str = config.get("Moduls", script_name, fallback="true").strip().lower()
    if enabled_str in valueOff:
        log_message(f"Skipping module {script_name} as it is disabled in the configuration.", level="info")
        continue
    elif enabled_str not in valueOn:
        log_message(f"Module {script_name} has unrecognized value '{enabled_str}' in configuration. Defaulting to enabled.", level="warning")

    # Überprüfe, ob das Skript existiert
    if not os.path.exists(script_path):
        log_message(f"{script_name} not found! Script will terminate.", level="error")
        sys.exit(1)

    log_message(f"Launching script: {shorten_path_last_n(script_path, 2)}", level="info")

    try:
        # Starte das Skript mit dem aktuellen Testverzeichnis als Argument
        subprocess.run(["python", script_path, current_test_directory], check=True)
        log_message(f"{script_name} finished successfully.", level="info")
    except subprocess.CalledProcessError as e:
        log_message(f"Script {script_name} execution failed: {e}", level="error")
        sys.exit(1)

log_separator()

# Nach Ablauf aller Vorgänge: Falls in der INI aktiviert, erst nach Betätigung der Enter-Taste beenden.
enter_confirmation_str = config.get("Settings", "enter_confirmation", fallback="false").strip().lower()
if enter_confirmation_str in ["true", "1", "yes", "on"]:
    input("Drücken Sie die Enter-Taste, um das Programm zu beenden...")
