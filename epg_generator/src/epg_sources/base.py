"""
EPG Source Base Class

Abstract base class defining the interface for all EPG data sources.
"""
from abc import ABC, abstractmethod
from models.epg_model import ProgramGuide


class EPGSource(ABC):
    """
    Abstract base class for EPG data sources.

    All EPG source implementations (SkyNZ, XMLTV, etc.) should inherit from this
    class and implement the get_program_guide() method.
    """

    def __init__(self, url: str, title: str):
        """
        Initialize the EPG source.

        Args:
            url: Source URL for fetching EPG data
            title: Descriptive title for this EPG source
        """
        self.url = url
        self.title = title

    @abstractmethod
    def get_program_guide(self) -> ProgramGuide:
        """
        Fetch and parse EPG data, returning a ProgramGuide object.

        This method must be implemented by all subclasses. It should:
        1. Fetch data from the source (API, XML feed, etc.)
        2. Parse the data into the appropriate format
        3. Return a fully populated ProgramGuide object

        Returns:
            ProgramGuide: Complete EPG data structured for LG ProCentric

        Raises:
            Exception: If fetching or parsing fails
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit - for future resource cleanup."""
        pass
