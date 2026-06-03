"""Category and item-type enumerations for the ASRA matcher."""
from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    A1 = "A1"  # Education K–Grade 6
    A2 = "A2"  # Education Grade 8–High School (Grade 7 default-mapped to A2)
    A3 = "A3"  # Post-secondary
    B = "B"    # Healthcare
    C = "C"    # Employment
    D = "D"    # Seniors
    E = "E"    # Personal browsing
    F = "F"    # Newcomers


CATEGORY_LABELS = {
    Category.A1: "Education — K to Grade 6",
    Category.A2: "Education — Grade 8 through high school",
    Category.A3: "Education — Post-secondary",
    Category.B: "Healthcare",
    Category.C: "Employment",
    Category.D: "Seniors",
    Category.E: "Personal browsing",
    Category.F: "Newcomers (recent immigrants)",
}


class A3SubTrack(str, Enum):
    ARTS = "arts"
    SCIENCE = "science"
    SOFTWARE_ENGINEERING = "software_engineering"
    BUSINESS = "business"


class DeviceTier(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    OTHER = "OTHER"


TIER_RANK = {DeviceTier.T1: 3, DeviceTier.T2: 2, DeviceTier.T3: 1, DeviceTier.OTHER: 0}


class OSChoice(str, Enum):
    """Q1 — operating system the applicant wants on the computer.

    Not a column in the inventory sheet (refurbished PCs are imaged on
    distribution), so it acts as a capability filter: Ubuntu runs on almost
    anything, Windows 11 needs a recent-enough CPU + adequate RAM, and "both"
    must clear the Windows bar.
    """

    UBUNTU = "ubuntu"
    WINDOWS = "windows"
    BOTH = "both"


class ItemType(str, Enum):
    COMPUTER = "computer"
    INPUT = "input"
    DISPLAY = "display"
    AUDIO = "audio"
    MOBILE = "mobile"
    CONNECTIVITY = "connectivity"


PERIPHERAL_TYPES = {
    ItemType.INPUT,
    ItemType.DISPLAY,
    ItemType.AUDIO,
    ItemType.CONNECTIVITY,
}


class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


URGENCY_WINDOW_DAYS = {
    Urgency.CRITICAL: 7,
    Urgency.HIGH: 30,
    Urgency.MEDIUM: 60,
    Urgency.LOW: 90,
}


class DeviceSituation(str, Enum):
    NONE = "none"
    PHONE_ONLY = "phone_only"
    SHARED_DEVICE = "shared_device"
    OUTDATED_DEVICE = "outdated_device"
