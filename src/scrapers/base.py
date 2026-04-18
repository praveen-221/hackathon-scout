"""
Base scraper interface and factory
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
import re

import aiohttp

from ..models import Hackathon, SourceName, HackathonMode


logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for scrapers"""

    source_name: SourceName = SourceName.UNKNOWN

    def __init__(self, config=None):
        """
        Initialize scraper with optional source configuration.

        Args:
            config: SourceConfig dataclass with base_url, search_paths, keywords
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

        # Extract config values with fallbacks to class defaults
        if config:
            self.base_url = config.base_url or self._get_default_base_url()
            self.search_paths = (
                config.search_paths
                if config.search_paths
                else self._get_default_search_paths()
            )
            self.keywords = (
                config.keywords if config.keywords else self._get_default_keywords()
            )
        else:
            self.base_url = self._get_default_base_url()
            self.search_paths = self._get_default_search_paths()
            self.keywords = self._get_default_keywords()

    def _get_default_base_url(self) -> str:
        """Override in subclass for default base URL"""
        return ""

    def _get_default_search_paths(self) -> list:
        """Override in subclass for default search paths"""
        return []

    def _get_default_keywords(self) -> list:
        """Override in subclass for default keywords"""
        return []

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp session for making HTTP requests.
        Creates a new session if one doesn't exist.
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session if it exists"""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    @abstractmethod
    async def scrape(self) -> List[Hackathon]:
        """Scrape hackathons from the source"""
        pass

    def _extract_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string into datetime"""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Check for date range "Feb 26 - Apr 29, 2026" - try to extract both dates
        if " - " in date_str:
            parts = date_str.split(" - ")
            if len(parts) >= 2:
                # Try first part with current year if no year
                first = parts[0].strip()
                second = parts[1].strip()
                # Check if first part needs current year
                if "," not in first:
                    year = datetime.now().year
                    first = f"{first}, {year}"
                if "," not in second:
                    year = datetime.now().year
                    second = f"{second}, {year}"
                try:
                    return datetime.strptime(first, "%b %d, %Y")
                except ValueError:
                    pass

        # Try adding current year if year is missing
        if "," not in date_str:
            date_str = f"{date_str}, {datetime.now().year}"

        # Common formats
        formats = [
            "%b %d, %Y",
            "%B %d, %Y",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%d %b %Y",
            "%d %B %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Handle relative dates
        if "today" in date_str.lower():
            return datetime.now()
        elif "tomorrow" in date_str.lower():
            return datetime.now()

        self.logger.debug(f"Could not parse date: {date_str}")
        return None

    def _extract_mode(self, text: str) -> HackathonMode:
        """Determine hackathon mode from text"""
        text_lower = text.lower()

        if "online" in text_lower or "virtual" in text_lower:
            return HackathonMode.ONLINE
        elif "in-person" in text_lower or "offline" in text_lower:
            return HackathonMode.IN_PERSON
        elif "hybrid" in text_lower:
            return HackathonMode.HYBRID

        return HackathonMode.UNKNOWN

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        return text

    def _truncate(self, text: str, length: int = 500) -> str:
        """Truncate text to specified length"""
        if not text:
            return ""

        if len(text) <= length:
            return text

        return text[:length].rsplit(" ", 1)[0] + "..."


class ScraperFactory:
    """Factory for creating scraper instances"""

    _scrapers = {}
    logger = logging.getLogger(__name__)

    @classmethod
    def register(cls, name: str, scraper_class):
        """Register a scraper class"""
        cls._scrapers[name] = scraper_class

    @classmethod
    def create(cls, name: str, config=None) -> Optional[BaseScraper]:
        """
        Create a scraper instance by name.

        Args:
            name: Scraper name (e.g., 'devpost', 'hack2skill')
            config: SourceConfig dataclass with base_url, search_paths, keywords

        Returns:
            BaseScraper instance or None if not found
        """
        if name in cls._scrapers:
            return cls._scrapers[name](config=config)

        cls.logger.warning(f"Unknown scraper: {name}")
        return None

    @classmethod
    def get_available(cls) -> List[str]:
        """Get list of available scraper names"""
        return list(cls._scrapers.keys())


# Register scrapers
def register_scrapers():
    """Register all available scrapers"""
    # Import dedicated scrapers
    from .devpost_scraper import DevpostScraper
    from .unstop_scraper import UnstopScraper
    from .devfolio_scraper import DevfolioScraper
    from .mlh_scraper import MLHScraper
    from .hack2skill_scraper import Hack2SkillScraper
    from .reskill_scraper import ReSkillScraper
    from .whereuelevate_scraper import WhereUElevateScraper
    from .hackerearth_scraper import HackerEarthScraper
    from .devnovate_scraper import DevnovateScraper
    from .generic_scraper import GenericScraper

    # Register dedicated scrapers (priority over generic)
    ScraperFactory.register("devpost", DevpostScraper)
    ScraperFactory.register("unstop", UnstopScraper)
    ScraperFactory.register("devfolio", DevfolioScraper)
    ScraperFactory.register("mlh", MLHScraper)
    ScraperFactory.register("hack2skill", Hack2SkillScraper)
    ScraperFactory.register("reskill", ReSkillScraper)
    ScraperFactory.register("whereuelevate", WhereUElevateScraper)
    ScraperFactory.register("hackerearth", HackerEarthScraper)
    ScraperFactory.register("devnovate", DevnovateScraper)

    # Generic scraper as fallback for unknown sources
    ScraperFactory.register("generic", GenericScraper)
