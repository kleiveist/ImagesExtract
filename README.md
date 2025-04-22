# ImagesExtract

![Python](https://img.shields.io/badge/python-3.8%2B-blue)  
![License](https://img.shields.io/badge/license-MIT-green)

A modular Python project with a Flask web frontend and text extraction from images. ImagesExtract lets you drag & drop images and returns the recognized text via a REST API.

---

## Table of Contents

1. [Features](#features)  
2. [Requirements](#requirements)  
3. [Installation](#installation)  
4. [Configuration](#configuration)  
5. [Project Structure](#project-structure)  
6. [Usage](#usage)  
7. [Example](#example)  
8. [Tests](#tests)  
9. [Deployment](#deployment)  
10. [Contributing](#contributing)  
11. [License](#license)  

---

## Features

- **Modular Design**  
  Separation of core extraction logic and web API.  
- **Web Frontend**  
  Simple drag & drop interface for image upload.  
- **REST API**  
  `/api/extract` returns extracted text as JSON.  
- **Configurable**  
  Central settings via `config.yml` or legacy `settings.ini`.  
- **Example Images**  
  In the `examples/` folder for testing and demos.  
- **Automated Tests**  
  pytest scripts in the `tests/` directory.

---

## Requirements

- Python 3.8 or higher  
- pip  
- Optional: Docker (for container deployment)

---

## Installation

1. Clone the repository  
   ```bash
   git clone https://github.com/YOUR_USERNAME/ImagesExtract.git
   cd ImagesExtract
Create and activate a virtual environment

bash
Kopieren
Bearbeiten
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
Install dependencies

bash
Kopieren
Bearbeiten
pip install -r requirements.txt
Configuration
All settings are in config.yml. Example:

yaml
Kopieren
Bearbeiten
input_folder: "./examples"
output_folder: "./output"
log_level: "INFO"
max_image_size_mb: 5
Legacy settings can be placed in image_extractor/settings.ini.

Set environment variables (e.g. for database credentials):

bash
Kopieren
Bearbeiten
export FLASK_ENV=development
export SECRET_KEY="your-secret-key"
Project Structure
csharp
Kopieren
Bearbeiten
ImagesExtract/
├── .gitignore
├── README.md
├── requirements.txt
├── config.yml              # Central configuration
├── instance/
│   └── login.db            # Sensitive data
├── src/
│   ├── app.py              # Flask entrypoint
│   ├── __init__.py
│   └── blueprints/
│       └── extractor.py    # /api/extract route
├── image_extractor/        # Core logic package
│   ├── __init__.py
│   ├── convert.py          # Image format conversion
│   ├── folders.py          # Folder handling
│   ├── enhancement.py      # Image enhancement
│   ├── transback.py        # Reverse transformations
│   ├── extract.py          # Text extraction
│   ├── extract_gray.py     # Grayscale extraction
│   ├── clean_up.py         # Cleanup routines
│   ├── scale.py            # Scaling
│   ├── collation.py        # Collation
│   ├── logger.py           # Logging setup
│   ├── utils.py            # Helper functions
│   └── settings.ini        # Legacy defaults
├── examples/               # Example images
│   └── 250118__ar_farm_04.png
├── static/                 # Web assets (CSS/JS)
│   ├── css/
│   └── js/
├── templates/              # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   └── register.html
└── tests/                  # Automated tests
    ├── test_convert.py
    ├── test_extract.py
    └── test_routes.py
Usage
Start Flask server
bash
Kopieren
Bearbeiten
export FLASK_APP=src/app.py
export FLASK_ENV=development
flask run
The app will be available at http://127.0.0.1:5000/.

Drag & Drop in Browser
Open http://127.0.0.1:5000/ in your browser.

Drag an image onto the drop zone.

The extracted text appears in the output area.

API Example
bash
Kopieren
Bearbeiten
curl -X POST http://127.0.0.1:5000/api/extract \
  -F "image=@/path/to/image.png"
Response:

json
Kopieren
Bearbeiten
{"text": "Recognized text from the image…"}
Example
Use the images in examples/ for batch processing:

bash
Kopieren
Bearbeiten
python src/app.py --batch examples/ --output output/
Tests
Run automated tests with pytest:

bash
Kopieren
Bearbeiten
pytest --maxfail=1 --disable-warnings -q
Deployment
Docker
Build the image

bash
Kopieren
Bearbeiten
docker build -t imagesextract .
Run the container

bash
Kopieren
Bearbeiten
docker run -d -p 5000:5000 \
  -e FLASK_ENV=production \
  imagesextract
Heroku
Create a Procfile

less
Kopieren
Bearbeiten
web: gunicorn src.app:app
Deploy via Heroku CLI

bash
Kopieren
Bearbeiten
heroku create
git push heroku main
heroku config:set SECRET_KEY="your-secret-key"
Contributing
Contributions are welcome! Please open an issue before submitting a pull request.
Follow the Contributor Covenant and our Code of Conduct.

License
This project is licensed under the MIT License.
See the LICENSE file for details.
