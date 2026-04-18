"""
Devpost Scraper
Go equivalent: src/go/pkg/fetcher/devpost.go
API: https://devpost.com/api/hackathons
"""

import logging
from typing import List, Optional
from datetime import datetime

import aiohttp

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class DevpostScraper(BaseScraper):
    """Scraper for Devpost hackathons"""

    source_name = SourceName.DEVPOST

    def _get_default_base_url(self) -> str:
        return "https://devpost.com"

    def _get_default_search_paths(self) -> list:
        return ["/hackathons"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape Devpost API"""
        hackathons = []

        try:
            session = await self._get_session()

            url = "https://devpost.com/api/hackathons"

            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.warning(f"Devpost returned {response.status}")
                    return []

                data = await response.json()

            items = data.get("hackathons", [])

            for item in items:
                hackathon = self._parse_item(item)
                if hackathon:
                    hackathons.append(hackathon)

            self.logger.info(f"Scraped {len(hackathons)} from Devpost")

        except Exception as e:
            self.logger.error(f"Devpost scrape failed: {e}")

        finally:
            await self.close()

        return hackathons

    def _parse_item(self, item: dict) -> Optional[Hackathon]:
        """Parse a Devpost hackathon item"""

        name = item.get("title", "")
        if not name:
            return None

        url = item.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://devpost.com{url}"

        # Parse dates from submission_period_dates: "Feb 26 - Apr 29, 2026"
        period_dates = item.get("submission_period_dates", "")
        start_date = None
        end_date = None
        if period_dates:
            # Try to parse date range "Feb 26 - Apr 29, 2026"
            if " - " in period_dates:
                parts = period_dates.split(" - ")
                if len(parts) == 2:
                    start_date = self._extract_date(parts[0].strip())
                    end_date = self._extract_date(parts[1].strip())
            if not start_date:
                start_date = self._extract_date(period_dates)
            if not end_date:
                end_date = self._extract_date(period_dates)

        # Also try direct fields
        if not start_date:
            start_date = self._extract_date(item.get("start_date", ""))
        if not end_date:
            reg_end = item.get("registration_end_date", "")
            if reg_end:
                end_date = self._extract_date(reg_end)

        # Location
        location = item.get("displayed_location", {})
        location_str = ""
        if isinstance(location, str):
            location_str = location
        elif isinstance(location, dict):
            location_str = location.get("location", "")

        # Mode - determine from location
        mode = HackathonMode.ONLINE
        if location_str and "online" not in location_str.lower():
            mode = HackathonMode.IN_PERSON

        # Prize - clean HTML tags
        prize = item.get("prize_amount", "")
        if prize:
            # Remove HTML tags like $<span data-currency-value>10,000</span>
            import re
            prize = re.sub(r'<[^>]+>', '', prize).strip()

        # Tags from themes
        themes = item.get("themes", [])
        tags = ["devpost"]
        for theme in themes:
            if isinstance(theme, dict):
                theme_name = theme.get("name", "")
                if theme_name:
                    tags.append(theme_name)
            elif isinstance(theme, str):
                tags.append(theme)

        # Description
        description = ""
        if item.get("organization_name"):
            description = f"Organized by {item.get('organization_name')}"

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            mode=mode,
            venue=location_str,
            prize_pool=prize,
            tags=tags,
            description=description,
            scraped_at=datetime.now(),
        )