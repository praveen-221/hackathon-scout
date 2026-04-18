"""Hackathon Scout - A hackathon discovery and notification tool"""

__version__ = "1.0.0"
__author__ = "The Builder"

from .config import ConfigManager
from .models import Hackathon, HackathonMode, SourceName
from .storage import StorageManager
from .orchestrator import HackathonScraper
from .emailer import EmailNotifier
from .scrapers import ScraperFactory

__all__ = [
    "ConfigManager",
    "Hackathon",
    "HackathonMode",
    "SourceName",
    "StorageManager",
    "HackathonScraper",
    "EmailNotifier",
    "ScraperFactory",
]
