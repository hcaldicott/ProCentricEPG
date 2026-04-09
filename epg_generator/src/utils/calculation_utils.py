"""
Calculation Utilities

Shared functions for calculating EPG-related metrics.
"""
import logging


def calculate_total_event_minutes(channels) -> int:
    """
    Calculate the total minutes across all events in all channels.

    This was previously named get_max_minutes() but the name was misleading
    as it sums (not finds max) all event durations.

    Args:
        channels: List of Channel objects with events

    Returns:
        Total minutes across all events
    """
    total_minutes = 0

    for channel in channels:
        for event in channel.events:
            try:
                # Ensure the event length is valid before adding
                total_minutes += int(event.length)
            except (ValueError, TypeError):
                # If length is not a valid integer, treat it as 0
                logging.warning(
                    f"Invalid length '{event.length}' for event {event.eventID}. "
                    f"Treating as 0 minutes."
                )

    return total_minutes
