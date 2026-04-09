"""
Text Processing Utilities

Shared functions for cleaning and safely extracting text from various data sources.
"""
import re


def clean_string(input_string: str) -> str:
    """
    Remove unsupported characters and normalize text.

    Args:
        input_string: String to clean

    Returns:
        Cleaned string with only ASCII characters
    """
    # Remove non-ASCII characters
    cleaned_string = re.sub(r'[^\x00-\x7F]+', '', input_string)
    # Replace specific characters with standard ones (e.g., \u2019 -> regular apostrophe)
    cleaned_string = cleaned_string.replace('\u2019', "'")
    cleaned_string = cleaned_string.replace('\u2026', "...")
    return cleaned_string


def safe_find_text_dict(parent: dict, key: str, default: str = "") -> str:
    """
    Safely extract text from a dictionary with cleaning.

    Args:
        parent: Dictionary to search
        key: Key to look for
        default: Default value if key not found

    Returns:
        Cleaned string value or default
    """
    if not isinstance(parent, dict):
        return clean_string(str(default))

    value = str(parent.get(key, default))
    return clean_string(value)


def safe_find_text_xml(parent, tag: str, default: str = "") -> str:
    """
    Safely extract text from an XML element.

    Args:
        parent: XML element to search
        tag: Tag name to find
        default: Default value if tag not found

    Returns:
        Text content of element or default
    """
    if parent is None:
        return default

    element = parent.find(tag)
    return element.text if element is not None and element.text else default


def safe_find_rating_value_xml(parent) -> str:
    """
    Safely extract rating value from XML <rating><value>...</value></rating> structure.

    Args:
        parent: XML element containing rating

    Returns:
        Rating value or empty string
    """
    if parent is None:
        return ""

    rating_elem = parent.find('rating')
    if rating_elem is not None:
        value_elem = rating_elem.find('value')
        if value_elem is not None:
            return value_elem.text or ""

    return ""
