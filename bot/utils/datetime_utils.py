"""Datetime utilities for consistent timezone handling."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """
    Get current UTC time as a timezone-aware datetime.
    
    This replaces datetime.utcnow() which returns naive datetimes.
    Using timezone-aware datetimes prevents comparison errors and is best practice.
    
    Returns:
        datetime: Current UTC time with timezone info
    """
    return datetime.now(timezone.utc)


def from_timestamp(timestamp: int | float) -> datetime:
    """
    Convert a Unix timestamp to a timezone-aware UTC datetime.
    
    Args:
        timestamp: Unix timestamp (seconds since epoch)
        
    Returns:
        datetime: Timezone-aware datetime in UTC
    """
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)

