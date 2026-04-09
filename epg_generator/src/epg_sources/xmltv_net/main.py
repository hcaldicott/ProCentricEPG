"""
XMLTV.net EPG Data Source

This module fetches EPG data from XMLTV.net XML feeds and transforms it into
the LG ProCentric format for various Australian cities.
"""
import random
import string
import logging
import requests
import pytz
import xml.etree.ElementTree as ET
from datetime import datetime
from models.epg_model import ProgramGuide, Channel, Event
from utils.text_utils import safe_find_text_xml, safe_find_rating_value_xml
from utils.calculation_utils import calculate_total_event_minutes

class XMLTV:
    def __init__(self, url: str, title: str, timezone: int = 0):
        self.url = url
        self.title = title
        self.timezone = timezone

    def get_fetch_time(self) -> str:
        """Returns the current timestamp in the required format with timezone offset."""
        # Get the current time in the local timezone (you can adjust the timezone if needed)
        local_tz = pytz.timezone("Australia/Sydney")  # Adjust to your local timezone
        now = datetime.now(local_tz)

        # Format the datetime with the required format
        return now.strftime("%Y-%m-%dT%H:%M:%S%z")

    def fetch_xml_data(self) -> str:
        """Fetch XML data from the provided URL with headers."""
        logging.info(f"Fetching XML data from {self.url}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        try:
            response = requests.get(self.url, headers=headers, timeout=60)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            return response.text
        except requests.exceptions.Timeout:
            raise Exception(f"Timeout while fetching XML data from {self.url}. Request took longer than 60 seconds.")
        except requests.exceptions.ConnectionError:
            raise Exception(f"Connection error while fetching XML data from {self.url}. Check network connectivity.")
        except requests.exceptions.HTTPError:
            raise Exception(f"HTTP error while fetching XML data. Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error fetching XML data from {self.url}: {e}")

    def generate_random_string(self, length=6) -> str:
        """Generate a random string of the given length."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


    def parse_xml_to_model(self, xml_data: str) -> ProgramGuide:
        """Parse the XML data and map it to the ProgramGuide Pydantic model."""
        logging.info(f"Parsing the XML data for {self.title}...")
        root = ET.fromstring(xml_data)

        # Build index of programmes by channel ID for O(N+M) performance instead of O(N*M)
        logging.debug("Building programme index by channel...")
        programmes_by_channel = {}
        for programme_elem in root.findall('programme'):
            channel_id = programme_elem.attrib.get('channel')
            if channel_id:
                if channel_id not in programmes_by_channel:
                    programmes_by_channel[channel_id] = []
                programmes_by_channel[channel_id].append(programme_elem)

        # Extract channel information
        channels = []
        for channel_elem in root.findall('channel'):
            channel_id = channel_elem.get('id')
            channel = Channel(
                channelID=channel_id,
                name=safe_find_text_xml(channel_elem, 'display-name'),
                resolution="HD",  # Assume resolution is HD for now (update if needed)
                events=[]
            )

            # Get programmes for this channel from the index
            channel_programmes = programmes_by_channel.get(channel_id, [])

            # Extract program information
            for programme_elem in channel_programmes:
                try:
                    start = programme_elem.get('start')  # Format: "YYYYMMDDHHMMSS Z"
                    stop = programme_elem.get('stop')

                    if not start or not stop:
                        logging.warning(f"Skipping programme with missing start/stop time for channel {channel_id}")
                        continue

                    # Convert start time to local timezone
                    utc_time = datetime.strptime(start, "%Y%m%d%H%M%S %z")  # Parse with timezone
                    local_tz = pytz.FixedOffset(self.timezone * 60)  # Convert minutes offset to tzinfo
                    local_time = utc_time.astimezone(local_tz)  # Convert to local time

                    formatted_date = local_time.strftime("%Y-%m-%d")  # Extract date
                    start_time = local_time.strftime("%H%M")  # Extract time in HH:MM format

                    event = Event(
                        eventID=self.generate_random_string(),
                        title=safe_find_text_xml(programme_elem, 'title'),
                        eventDescription=safe_find_text_xml(programme_elem, 'desc'),
                        rating=safe_find_rating_value_xml(programme_elem),
                        date=formatted_date,
                        startTime=start_time,
                        length=str(int((datetime.strptime(stop, "%Y%m%d%H%M%S %z") - utc_time).total_seconds() // 60)),
                        genre=safe_find_text_xml(programme_elem, 'category')
                    )
                    channel.events.append(event)
                except (ValueError, KeyError, AttributeError) as e:
                    logging.warning(f"Error parsing programme for channel {channel_id}: {e}")
                    continue

            channels.append(channel)

        # Now calculate the maxMinutes by passing the ProgramGuide object
        program_guide = ProgramGuide(
            filetype=self.title,
            version="1.0",
            fetchTime=self.get_fetch_time(),
            maxMinutes=calculate_total_event_minutes(channels),
            channels=channels
        )

        return program_guide

    def get_program_guide(self) -> ProgramGuide:
        """Fetch the XML and parse it into the ProgramGuide model."""
        logging.info(f"Getting program guide for {self.title}...")
        xml_data = self.fetch_xml_data()
        return self.parse_xml_to_model(xml_data)
