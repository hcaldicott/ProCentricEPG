"""
File Handling Utilities

This module provides functions for saving EPG data as JSON files and creating
ZIP archives for LG ProCentric distribution.
"""
import datetime
import json
import logging
import os
import zipfile
from pathlib import Path
from models.epg_model import ProgramGuide  # Import your model

# Use /bundles if running in Docker, otherwise use output
BASE_OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))  # Base output directory

def save_json(data: ProgramGuide, subdirs: list[str]) -> Path:
    """Save the program guide data as 'Procentric_EPG.json' inside subdirectories."""

    output_path = BASE_OUTPUT_DIR.joinpath(*subdirs)
    output_path.mkdir(parents=True, exist_ok=True)  # Ensure directories exist

    json_path = output_path / "Procentric_EPG.json"  # Fixed filename

    try:
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data.dict() if hasattr(data, 'dict') else data, f, indent=4)
        logging.info(f"JSON saved: {json_path}")
    except Exception as e:
        logging.error(f"Error saving JSON: {e}")
        return None

    return json_path


def zip_json(json_path: Path, zip_filename: str) -> Path:
    """Zip the JSON file with a custom ZIP filename including today's date,
    delete the original JSON file, and remove older versions of the ZIP file."""

    today_date = datetime.datetime.now().strftime("%Y%m%d")  # Format: YYYYMMDD
    zip_filename_with_date = f"{zip_filename}_{today_date}.zip"
    zip_path = json_path.parent / zip_filename_with_date  # Custom ZIP name with today's date

    # Remove older ZIP files in the directory (excluding today's ZIP)
    for file in json_path.parent.glob(f"{zip_filename}_*.zip"):
        if file != zip_path:
            try:
                file.unlink()
                logging.info(f"Deleted old ZIP: {file}")
            except Exception as e:
                logging.error(f"Error deleting old ZIP {file}: {e}")

    # Create new ZIP
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(json_path, json_path.name)
        logging.info(f"ZIP created: {zip_path}")
    except Exception as e:
        logging.error(f"Error creating ZIP: {e}")
        return None

    # Delete the JSON file after zipping
    try:
        json_path.unlink()
        logging.info(f"Deleted JSON file: {json_path}")
    except Exception as e:
        logging.error(f"Error deleting JSON file: {e}")

    return zip_path


def save_and_zip(data: ProgramGuide, subdirs: list[str], zip_filename: str) -> Path:
    """Save JSON as 'Procentric_EPG.json' and create a ZIP file with a custom name, then delete the JSON file."""

    json_path = save_json(data, subdirs)
    if not json_path:
        logging.error("Failed to save JSON. Skipping ZIP creation.")
        return None

    zip_path = zip_json(json_path, zip_filename)
    return zip_path
