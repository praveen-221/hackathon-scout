"""
WhereUElevate Scraper
Go equivalent: src/go/pkg/fetcher/whereuelevate.go
API: https://api.whereuelevate.com/internity/api/v1/drills/search
"""

import logging
from typing import List, Optional
from datetime import datetime

import aiohttp

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class WhereUElevateScraper(BaseScraper):
    """Scraper for WhereUElevate hackathons"""

    source_name = SourceName.WHEREUELEVATE

    def _get_default_base_url(self) -> str:
        return "https://whereuelevate.com"

    def _get_default_search_paths(self) -> list:
        return ["/drills"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape WhereUElevate API"""
        hackathons = []

        try:
            session = await self._get_session()

            url = (
                "https://api.whereuelevate.com/internity/api/v1/drills/search"
                "?drillCategory=HACKATHON&drillId=all&limit=30&mode=all&offset=0&order=DESC"
                "&status=all&type=all&isActive=true&hideFromUserListing=false"
            )

            headers = session.headers.copy()
            headers.update({
                "Accept": "application/json",
                "Referer": "https://whereuelevate.com/drills",
                "Origin": "https://whereuelevate.com",
            })

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.warning(f"WhereUElevate returned {response.status}")
                    return []

                data = await response.json()

            # Extract drills
            drills = []
            if "data" in data:
                if isinstance(data["data"], dict):
                    drills = data["data"].get("drills", [])
                    if not drills:
                        drills = data["data"].get("content", [])
                elif isinstance(data["data"], list):
                    drills = data["data"]

            for item in drills:
                hackathon = self._parse_item(item)
                if hackathon:
                    hackathons.append(hackathon)

            self.logger.info(f"Scraped {len(hackathons)} from WhereUElevate")

        except Exception as e:
            self.logger.error(f"WhereUElevate scrape failed: {e}")

        finally:
            await self.close()

        return hackathons

    def _parse_item(self, item: dict) -> Optional[Hackathon]:
        """Parse a WhereUElevate item"""

        name = item.get("title", "")
        if not name:
            name = item.get("drillTitle", "") or item.get("drillName", "")
        if not name:
            return None

        # URL/slug
        slug = item.get("slug", "") or item.get("drillCustUrl", "")
        if slug:
            url = f"https://whereuelevate.com/drills/{slug}"
        else:
            url = ""

        # Mode - check drillNature for hybrid/online
        drill_nature = item.get("drillNature", "")
        if drill_nature.lower() == "online":
            mode = HackathonMode.ONLINE
        elif drill_nature.lower() == "hybrid":
            mode = HackathonMode.HYBRID
        else:
            mode = HackathonMode.IN_PERSON

        # Location
        location = item.get("location", "") or item.get("drillLocation", "")

        # Dates - try ISO format first
        start_date = self._parse_iso_date(item.get("startDate", ""))
        if not start_date:
            start_date = self._parse_iso_date(item.get("drillStartDate", ""))
            if not start_date:
                start_date = self._parse_iso_date(item.get("drillStartDt", ""))

        end_date = self._parse_iso_date(item.get("endDate", ""))
        if not end_date:
            end_date = self._parse_iso_date(item.get("drillEndDate", ""))
            if not end_date:
                end_date = self._parse_iso_date(item.get("drillEndDt", ""))

        # Registration deadline
        reg_end = self._parse_iso_date(item.get("drillRegistrationEndDt", ""))

        # Prize pool
        prize_pool = item.get("totalPrizeValue", "")

        # Tags
        tags = ["whereuelevate"]
        category = item.get("drillCategory", "")
        if category:
            tags.append(category)
        subcategory = item.get("drillSubCategory", "")
        if subcategory:
            tags.append(subcategory)

        # Description
        description = ""
        highlights = item.get("drillKeyHighlights", "")
        if highlights:
            import re
            # Remove HTML tags
            description = re.sub(r'<[^>]+>', '', highlights)[:500]

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            registration_deadline=reg_end,
            mode=mode,
            venue=location,
            prize_pool=str(prize_pool) if prize_pool else "",
            tags=tags,
            description=description,
            scraped_at=datetime.now(),
        )

    def _parse_iso_date(self, date_str: str) -> Optional[datetime]:
        """Parse ISO format dates"""
        if not date_str:
            return None
        try:
            # Format: "2026-04-09T06:25:00"
            return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError):
            return self._parse_date(date_str)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse WhereUElevate date format"""
        if not date_str:
            return None

        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return self._extract_date(date_str)