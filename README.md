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

