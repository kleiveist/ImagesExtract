ImagesExtract

Python
License

A modular Python project with a Flask web frontend and text extraction from images. ImagesExtract lets you drag & drop images and returns the recognized text via a REST API.
Table of Contents

    Features
    Requirements
    Installation
    Configuration
    Project Structure
    Usage
    Example
    Tests
    Deployment
    Contributing
    License

Features

    Modular Design
    Separation of core extraction logic and web API.
    Web Frontend
    Simple drag & drop interface for image upload.
    REST API
    /api/extract returns extracted text as JSON.
    Configurable
    Central settings via config.yml or legacy settings.ini.
    Example Images
    In the examples/ folder for testing and demos.
    Automated Tests
    pytest scripts in the tests/ directory.

Requirements

    Python 3.8 or higher
    pip
    Optional: Docker (for container deployment)

Installation
Clone the repository

git clone https://github.com/YOUR_USERNAME/ImagesExtract.git
cd ImagesExtract

Create and activate a virtual environment
