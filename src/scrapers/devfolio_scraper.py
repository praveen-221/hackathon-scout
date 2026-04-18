"""
Devfolio Scraper
Go equivalent: src/go/pkg/fetcher/devfolio.go
Extracts embedded JSON from HTML page
"""

import logging
from typing import List, Optional
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup
import re

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class DevfolioScraper(BaseScraper):
    """Scraper for Devfolio hackathons"""

    source_name = SourceName.DEVFOLIO

    def _get_default_base_url(self) -> str:
        return "https://devfolio.co"

    def _get_default_search_paths(self) -> list:
        return ["/hackathons"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape Devfolio - extracts embedded __NEXT_DATA__"""
        hackathons = []

        try:
            session = await self._get_session()

            url = "https://devfolio.co/hackathons"

            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.warning(f"Devfolio returned {response.status}")
                    return []

                html = await response.text()

            # Extract embedded __NEXT_DATA__ from script tag
            soup = BeautifulSoup(html, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")

            if not script:
                self.logger.warning("No __NEXT_DATA__ found")
                return []

            import json
            data = json.loads(script.string)

            # Extract hackathons from dehydrated state
            items = self._extract_hackathons(data)

            for item in items:
                hackathon = self._parse_item(item)
                if hackathon:
                    hackathons.append(hackathon)

            self.logger.info(f"Scraped {len(hackathons)} from Devfolio")

        except Exception as e:
            self.logger.error(f"Devfolio scrape failed: {e}")

        finally:
            await self.close()

        return hackathons

    def _extract_hackathons(self, data: dict) -> list:
        """Extract hackathon data from Next.js data structure"""
        items = []

        try:
            if "props" in data:
                page_props = data.get("props", {}).get("pageProps", {})
                dehydrated = page_props.get("dehydratedState", {})
                queries = dehydrated.get("queries", [])

                for query in queries:
                    state = query.get("state", {})
                    hackathons = state.get("data", {}).get("open_hackathons", [])
                    items.extend(hackathons)
        except Exception as e:
            self.logger.debug(f"Failed to extract: {e}")

        return items

    def _parse_item(self, item: dict) -> Optional[Hackathon]:
        """Parse a Devfolio hackathon item"""

        name = item.get("name", "")
        if not name:
            return None

        slug = item.get("slug", "")
        url = f"https://devfolio.co/hackathons/{slug}" if slug else ""

        # Dates - handle ISO format
        start_date = self._extract_date(item.get("starts_at", "") or item.get("start_date", ""))
        end_date = self._extract_date(item.get("ends_at", "") or item.get("end_date", ""))

        # Registration deadline from settings
        settings = item.get("settings", {})
        if not end_date:
            reg_ends = settings.get("reg_ends_at", "") if settings else ""
            if reg_ends:
                end_date = self._extract_date(reg_ends)

        # Mode - check timezone for hybrid detection
        timezone = item.get("timezone", "")
        is_online = item.get("is_online", False)
        if is_online:
            mode = HackathonMode.ONLINE
        elif timezone and "online" in str(timezone).lower():
            mode = HackathonMode.ONLINE
        else:
            mode = HackathonMode.IN_PERSON

        # Location
        venue = item.get("location", "")

        # Tags - from themes
        themes = item.get("themes", [])
        tags = ["devfolio"]
        for theme in themes:
            if isinstance(theme, dict):
                theme_name = theme.get("theme", {}).get("name", "")
                if theme_name:
                    tags.append(theme_name)
            elif isinstance(theme, str):
                tags.append(theme)

        # Description from organization
        org = item.get("organisation", {})
        description = ""
        if org:
            org_name = org.get("name", "")
            if org_name:
                description = f"Organized by {org_name}"

        # Prize pool
        prize_pool = ""
        prizes = item.get("prizes", [])
        if prizes:
            prize_parts = []
            for prize in prizes[:3]:
                amount = prize.get("prize_amount", "")
                if amount:
                    prize_parts.append(str(amount))
            if prize_parts:
                prize_pool = "$" + ", ".join(prize_parts)

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            mode=mode,
            venue=venue,
            prize_pool=prize_pool,
            tags=tags,
            description=description,
            scraped_at=datetime.now(),
        )