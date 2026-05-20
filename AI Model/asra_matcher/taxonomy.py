"""Canonical taxonomy: applicant categories, device tiers, item types."""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    """Applicant-side categories from the LGT framework."""

    A1 = "A1"  # K to grade 6
    A2 = "A2"  # Grade 8 through high school
    A3 = "A3"  # Post-secondary (has sub-track)
    B = "B"    # Healthcare
    C = "C"    # Employment
    D = "D"    # Seniors
    E = "E"    # Personal browsing
    F = "F"    # Newcomers


class A3Subtrack(str, Enum):
    ARTS = "arts"
    SCIENCE = "science"
    SOFTWARE_ENGINEERING = "software_engineering"
    BUSINESS = "business"


class DeviceTier(str, Enum):
    """Computer tier classification."""

    T1 = "T1"        # High Power
    T2 = "T2"        # Standard
    T3 = "T3"        # Basic / Essential
    OTHER = "OTHER"  # Doesn't fit the three tiers


class ItemType(str, Enum):
    """High-level device type."""

    COMPUTER = "computer"
    INPUT = "input"            # keyboard, mouse
    DISPLAY = "display"        # monitors
    AUDIO = "audio"            # headphones, microphones
    MOBILE = "mobile"          # phone, tablet, chromebook
    CONNECTIVITY = "connectivity"  # cables, chargers, USB


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TechAccess(str, Enum):
    """Applicant's current technology situation."""

    NONE = "none"
    PHONE_ONLY = "phone_only"
    SHARED_DEVICE = "shared_device"
    OUTDATED_DEVICE = "outdated_device"
    INTERNET_ONLY = "internet_only"


class PriorDeviceStatus(str, Enum):
    WORKING = "working"
    BROKEN = "broken"
    OUTGROWN = "outgrown"
    NA = "n/a"


# Tier ranks for efficiency scoring. Higher rank = more powerful.
TIER_RANK = {
    DeviceTier.T1: 3,
    DeviceTier.T2: 2,
    DeviceTier.T3: 1,
}

# Urgency window in days (used by timing score).
URGENCY_WINDOW_DAYS = {
    Urgency.CRITICAL: 7,
    Urgency.HIGH: 30,
    Urgency.MEDIUM: 60,
    Urgency.LOW: 90,
}
