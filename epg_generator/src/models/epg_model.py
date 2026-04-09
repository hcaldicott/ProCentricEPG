"""
EPG Data Models

This module defines Pydantic models for representing Electronic Program Guide (EPG)
data in the LG ProCentric format.
"""
from pydantic import BaseModel
from typing import List
from datetime import datetime

class Event(BaseModel):
    """Represents a single TV program/event."""
    eventID: str
    title: str
    eventDescription: str
    rating: str
    date: str  # Format: YYYY-MM-DD
    startTime: str  # Format: HHMM (24-hour time)
    length: str  # Duration in minutes
    genre: str

class Channel(BaseModel):
    """Represents a TV channel with its schedule of events."""
    channelID: str
    name: str
    resolution: str
    events: List[Event]

class ProgramGuide(BaseModel):
    """Represents the complete EPG program guide for LG ProCentric."""
    filetype: str
    version: str
    fetchTime: str
    maxMinutes: int
    channels: List[Channel]

def get_fetch_time() -> str:
    """Returns the current timestamp in ISO format with timezone offset."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
