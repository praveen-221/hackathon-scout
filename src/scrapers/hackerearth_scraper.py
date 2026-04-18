"""
HackerEarth Scraper
Go equivalent: src/go/pkg/fetcher/hackerearth.go
API: https://www.hackerearth.com/api/community/challenges/compete/
"""

import logging
from typing import List, Optional
from datetime import datetime

import aiohttp

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class HackerEarthScraper(BaseScraper):
    """Scraper for HackerEarth hackathons"""

    source_name = SourceName.HACKEREARTH

    def _get_default_base_url(self) -> str:
        return "https://www.hackerearth.com"

    def _get_default_search_paths(self) -> list:
        return ["/challenges/hackathon"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape HackerEarth API"""
        hackathons = []

        try:
            session = await self._get_session()

            url = "https://www.hackerearth.com/api/community/challenges/compete/?limit=100&status=UPCOMING"

            headers = session.headers.copy()
            headers.update({
                "Referer": "https://www.hackerearth.com/challenges/hackathon/",
            })

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.warning(f"HackerEarth returned {response.status}")
                    return []

                data = await response.json()

            # Extract challenges
            items = data.get("data", [])

            for item in items:
                # Filter only Hackathons
                if item.get("type", "") != "Hackathon":
                    continue

                hackathon = self._parse_item(item)
                if hackathon and hackathon.end_date and hackathon.end_date > datetime.now():
                    hackathons.append(hackathon)

            self.logger.info(f"Scraped {len(hackathons)} from HackerEarth")

        except Exception as e:
            self.logger.error(f"HackerEarth scrape failed: {e}")

        finally:
            await self.close()

        return hackathons

    def _parse_item(self, item: dict) -> Optional[Hackathon]:
        """Parse a HackerEarth item"""

        name = item.get("title", "")
        if not name:
            return None

        # URL
        url = item.get("url", "")
        slug = item.get("slug", "")

        if url and not url.startswith("http"):
            if slug:
                url = f"https://www.hackerearth.com/challenges/hackathon/{slug}/"
            else:
                url = f"https://www.hackerearth.com{url}"
        elif slug:
            url = f"https://www.hackerearth.com/challenges/hackathon/{slug}/"

        # Dates - try ISO first, then regular parsing
        start_date = self._parse_iso_date(item.get("start", ""))
        if not start_date:
            start_date = self._extract_date(item.get("start", ""))

        end_date = self._parse_iso_date(item.get("end", ""))
        if not end_date:
            end_date = self._extract_date(item.get("end", ""))

        # Tags from challenge type
        tags = ["hackerearth"]
        challenge_type = item.get("type", "")
        if challenge_type:
            tags.append(challenge_type)

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            mode=HackathonMode.ONLINE,
            tags=tags,
            scraped_at=datetime.now(),
        )

    def _parse_iso_date(self, date_str: str) -> Optional[datetime]:
        """Parse ISO format dates"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError):
            return self._extract_date(date_str)