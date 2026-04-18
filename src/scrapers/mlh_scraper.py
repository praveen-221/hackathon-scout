"""
MLH Scraper
Go equivalent: src/go/pkg/fetcher/mlh.go
HTML scraping from mlh.io/seasons/{year}/events
"""

import logging
from typing import List, Optional
from datetime import datetime
import re

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class MLHScraper(BaseScraper):
    """Scraper for MLH hackathons"""

    source_name = SourceName.MLH

    def _get_default_base_url(self) -> str:
        return "https://mlh.io"

    def _get_default_search_paths(self) -> list:
        return ["/seasons/2026/events"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape MLH events page"""
        hackathons = []

        try:
            session = await self._get_session()

            # Build URL with current/next season year
            current_year = datetime.now().year
            if datetime.now().month >= 7:
                current_year += 1
            
            url = f"https://mlh.io/seasons/{current_year}/events"
            self.logger.debug(f"Fetching MLH: {url}")

            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.warning(f"MLH returned {response.status}")
                    return []

                html = await response.text()

            soup = BeautifulSoup(html, "html.parser")

            # MLH uses .event-wrapper class
            for event_card in soup.select(".event-wrapper"):
                hackathon = self._parse_card(event_card)
                if hackathon:
                    hackathons.append(hackathon)

            self.logger.info(f"Scraped {len(hackathons)} from MLH")

        except Exception as e:
            self.logger.error(f"MLH scrape failed: {e}")

        finally:
            await self.close()

        return hackathons

    def _parse_card(self, card) -> Optional[Hackathon]:
        """Parse an MLH event card"""

        # Title
        title_elem = card.select_one(".event-name")
        name = title_elem.get_text(strip=True) if title_elem else ""
        if not name:
            return None

        # URL
        link_elem = card.select_one("a.event-link")
        url = link_elem.get("href", "") if link_elem else ""

        # Location
        location_elem = card.select_one(".event-location")
        location = location_elem.get_text(strip=True) if location_elem else ""

        # Date
        date_elem = card.select_one(".event-date")
        date_str = date_elem.get_text(strip=True) if date_elem else ""

        start_date, end_date = self._parse_mlh_date(date_str)

        # Mode
        mode = HackathonMode.IN_PERSON
        if location and "global" in location.lower():
            mode = HackathonMode.ONLINE

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            mode=mode,
            venue=location,
            tags=["mlh"],
            scraped_at=datetime.now(),
        )

    def _parse_mlh_date(self, date_str: str):
        """Parse MLH date format like 'Jan 25-26, 2025' or 'Mar 21-23'"""
        if not date_str:
            return None, None

        # Clean ordinal suffixes
        date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

        parts = date_str.split("-")
        if not parts:
            return None, None

        try:
            start_str = parts[0].strip()
            
            # Try "Jan 25, 2025" format
            start_date = datetime.strptime(start_str, "%b %d, %Y")
            
            if len(parts) > 1:
                end_str = parts[1].strip()
                # Check if year included
                if "," in end_str:
                    end_date = datetime.strptime(end_str, "%b %d, %Y")
                else:
                    # Add year from start
                    end_date = datetime.strptime(f"{end_str}, {start_date.year}", "%b %d, %Y")
            else:
                end_date = start_date

            return start_date, end_date

        except ValueError:
            # Try simpler format
            try:
                return datetime.strptime(date_str.strip(), "%b %d"), None
            except:
                return None, None