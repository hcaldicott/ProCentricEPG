"""
Sky NZ EPG Data Source

This module fetches EPG data from the Sky NZ GraphQL API and transforms it into
the LG ProCentric format.
"""
import logging
import requests
from datetime import datetime, timedelta
import pytz
from models.epg_model import ProgramGuide, Channel, Event, get_fetch_time
from utils.text_utils import safe_find_text_dict
from utils.calculation_utils import calculate_total_event_minutes


# Get current date in New Zealand time zone
nz_timezone = pytz.timezone("Pacific/Auckland")
nz_date = datetime.now(nz_timezone).strftime("%Y-%m-%d")

# Generate a list of dates for today and the next two days
nz_dates = [(datetime.now(nz_timezone) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]



class SkyNZ_EPG:
    def __init__(self, url: str, zip_output_path: str):
        self.url = url
        self.zip_output_path = zip_output_path

    def fetch_data(self):
        """Fetch data from the GraphQL endpoint."""

        headers = {
            'Content-Type': 'application/json',
        }

        merged_data = {
            "data": {
                "experience": {
                    "channelGroup": {
                        "channels": []
                    }
                }
            }
        }


        for nz_date in nz_dates:
            # Define the request body with the dynamic date
            logging.info(f"Fetching data for date: {nz_date}")

            body = {
                "query": """
                    query getChannelGroup($id: ID!, $date: LocalDate) {
                        experience(appId: TV_GUIDE_WEB) {
                            channelGroup(id: $id) {
                                id
                                title
                                channels {
                                    ... on LinearChannel {
                                        id
                                        title
                                        number
                                        tileImage {
                                            uri
                                        }
                                        slotsForDay(date: $date) {
                                            slots {
                                                id
                                                startMs
                                                endMs
                                                ratingString
                                                programme {
                                                    ... on Episode {
                                                        id
                                                        title
                                                        synopsis
                                                        show {
                                                            id
                                                            title
                                                            type
                                                        }
                                                    }
                                                    ... on Movie {
                                                        id
                                                        title
                                                        synopsis
                                                    }
                                                    ... on PayPerViewEventProgram {
                                                        id
                                                        title
                                                        synopsis
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                """,
                "variables": {
                    "id": "4b7LA20J4iHaThwky9iVqn",
                    "date": nz_date
                }
            }



            try:
                response = requests.post(self.url, headers=headers, json=body, timeout=30)
                response.raise_for_status()  # Raise exception for 4xx/5xx status codes

                # Extract channel list safely
                data = response.json()

                channels = (
                    data.get("data", {})
                    .get("experience", {})
                    .get("channelGroup", {})
                    .get("channels", [])
                )

                # Merge channels by appending them to the merged_data
                merged_data["data"]["experience"]["channelGroup"]["channels"].extend(channels)

            except requests.exceptions.Timeout:
                logging.error(f"Timeout while fetching data for {nz_date}. Request took longer than 30 seconds.")
                return None
            except requests.exceptions.ConnectionError:
                logging.error(f"Connection error while fetching data for {nz_date}. Check network connectivity.")
                return None
            except requests.exceptions.HTTPError:
                logging.error(f"HTTP error while fetching data for {nz_date}. Status code: {response.status_code}, Response: {response.text[:200]}")
                return None
            except requests.exceptions.RequestException as e:
                logging.error(f"Error fetching data for {nz_date}: {e}")
                return None
            except ValueError as e:
                logging.error(f"Error parsing JSON response for {nz_date}: {e}")
                return None

        return merged_data



    def parse_program_data(self, data):
        """Parse the response data from the GraphQL query and map it to the ProgramGuide model."""
        # Ensure we have the expected structure

        if 'data' not in data or 'experience' not in data['data'] or 'channelGroup' not in data['data']['experience']:
            logging.error("Unexpected data structure received from API")
            return None

        # Prepare the ProgramGuide model
        program_guide = ProgramGuide(
            filetype="Pro:Centric JSON Program Guide Data NZL",
            version="1.0",
            fetchTime=get_fetch_time(),
            maxMinutes=0,
            channels=[]
        )

        # Extract channel group and channels
        channel_group_data = data['data']['experience']['channelGroup']

        # Parse the channels
        for channel in channel_group_data['channels']:
            # Initialize Channel model
            channel_obj = Channel(
                channelID=channel['id'],
                name=channel['title'],
                resolution="HD",  # Default resolution, you might have to adjust if info is available
                events=[]
            )

            # Check if 'slotsForDay' exists and is a dictionary with the 'slots' key
            slots_for_day = channel.get('slotsForDay', {})
            if isinstance(slots_for_day, dict) and 'slots' in slots_for_day:
                for slot in slots_for_day['slots']:
                    # Map event data to the Event model

                    # Check if 'programme' and 'synopsis' exist before accessing
                    programme = slot.get('programme', {})
                    title = safe_find_text_dict(programme, 'title', '')  # Safe retrieval
                    event_description = safe_find_text_dict(programme, 'synopsis', '')  # Safe retrieval
                    rating = safe_find_text_dict(slot, 'ratingString', '')  # Safe retrieval

                    # Map event data to the Event model
                    event_obj = Event(
                        eventID=slot['id'],
                        title=title,  # Default to empty string if title is missing
                        eventDescription=event_description,
                        rating=rating, # If ratings are available, map them here
                        date=self.format_date(slot['startMs']),  # Ensure correct date format
                        startTime=self.format_start_time(slot['startMs']),  # Convert start time from ms
                        length=self.calculate_length(slot['startMs'], slot['endMs']),  # Duration in minutes
                        genre= ""
                    )

                    # Add the event to the channel's event list
                    channel_obj.events.append(event_obj)
            else:
                # Log a more detailed warning if 'slotsForDay' is not in the expected format
                logging.warning(f"'slotsForDay' is not valid or missing for channel: {channel['title']}")

            # Add the channel to the ProgramGuide's channel list
            program_guide.channels.append(channel_obj)

        program_guide.maxMinutes = calculate_total_event_minutes(program_guide.channels)

        return program_guide


    def format_start_time(self, start_ms: int) -> str:
        """Convert start time in milliseconds to HHMM (24-hour format)."""
        start_time = datetime.utcfromtimestamp(start_ms / 1000)  # Convert ms to seconds
        return start_time.strftime("%H%M")

    def calculate_length(self, start_ms: int, end_ms: int) -> str:
        """Calculate the duration in minutes."""
        duration = (end_ms - start_ms) / 60000  # Convert milliseconds to minutes
        return str(int(duration))


    def format_date(self, timestamp_ms):
        """Convert a timestamp in milliseconds to a human-readable date format (YYYY-MM-DD)."""
        # Convert milliseconds to seconds
        timestamp_sec = timestamp_ms / 1000.0
        # Create a datetime object from the timestamp
        dt = datetime.utcfromtimestamp(timestamp_sec)
        # Return the formatted date as a string (e.g., '2023-03-23')
        return dt.strftime('%Y-%m-%d')
