"""
Hack2Skill Scraper
Go equivalent: src/go/pkg/fetcher/hack2skill.go
API: https://vision.hack2skill.com/api/v1/innovator/public/event/public-list
"""

import logging
from typing import List, Optional
from datetime import datetime

import aiohttp

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class Hack2SkillScraper(BaseScraper):
    """Scraper for Hack2Skill hackathons"""

    source_name = SourceName.HACK2SKILL

    def _get_default_base_url(self) -> str:
        return "https://vision.hack2skill.com"

    def _get_default_search_paths(self) -> list:
        return ["/hackathons-listing"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape Hack2Skill API"""
        hackathons = []

        try:
            session = await self._get_session()

            # Build date range
            start = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            end = datetime.now().replace(year=datetime.now().year + 2).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            url = f"https://vision.hack2skill.com/api/v1/innovator/public/event/public-list?page=1&records=50&search=&start={start}&end={end}"

            # Add custom headers
            headers = session.headers.copy()
            headers.update({
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://vision.hack2skill.com/hackathons-listing",
                "Origin": "https://vision.hack2skill.com",
            })

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.warning(f"Hack2Skill returned {response.status}")
                    # Fallback to HTML scraping
                    return await self._scrape_html()

                data = await response.json()

            # Extract docs
            docs = []
            if "data" in data:
                if isinstance(data["data"], dict):
                    docs = data["data"].get("docs", [])
                elif isinstance(data["data"], list):
                    docs = data["data"]

            if not docs:
                return await self._scrape_html()

            for item in docs:
                hackathon = self._parse_item(item)
                if hackathon:
                    hackathons.append(hackathon)

            self.logger.info(f"Scraped {len(hackathons)} from Hack2Skill")

        except Exception as e:
            self.logger.error(f"Hack2Skill scrape failed: {e}")
            # Fallback to HTML
            return await self._scrape_html()

        finally:
            await self.close()

        return hackathons

    async def _scrape_html(self) -> List[Hackathon]:
        """Fallback HTML scraping"""
        hackathons = []

        try:
            session = await self._get_session()
            url = "https://hack2skill.com/hackathons"

            async with session.get(url) as response:
                if response.status != 200:
                    return []

                html = await response.text()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            for card in soup.select("div.new-card, div.event-card, a[href*='/hackathons/']"):
                link = card.get("href", "")
                if not link:
                    continue

                title = card.select_one("h3, .title, .event-title")
                name = title.get_text(strip=True) if title else ""
                if not name:
                    name = card.get_text(strip=True)[:100]

                if len(name) < 5:
                    continue

                hackathons.append(Hackathon(
                    name=name[:200],
                    source=self.source_name,
                    url=link,
                    mode=HackathonMode.ONLINE,
                    tags=["hack2skill"],
                    scraped_at=datetime.now(),
                ))

        except Exception as e:
            self.logger.error(f"Hack2Skill HTML fallback failed: {e}")

        return hackathons

    def _parse_item(self, item: dict) -> Optional[Hackathon]:
        """Parse a Hack2Skill item"""

        name = item.get("title", "")
        if not name:
            return None

        # Get URL/slug
        slug = item.get("eventUrl", "") or item.get("slug", "") or item.get("event_slug", "")
        event_id = item.get("id") or item.get("_id", "")

        if slug:
            url = f"https://vision.hack2skill.com/event/{slug}"
        elif event_id:
            url = f"https://vision.hack2skill.com/event/{event_id}"
        else:
            url = ""

        # Dates - Parse ISO format from API: "2026-04-10T04:30:00.000Z"
        # Try both registration and submission dates
        sub_start = self._parse_iso_date(item.get("submissionStart", ""))
        sub_end = self._parse_iso_date(item.get("submissionEnd", ""))
        reg_start = self._parse_iso_date(item.get("registrationStart", ""))
        reg_end = self._parse_iso_date(item.get("registrationEnd", ""))

        start_date = sub_start or reg_start
        end_date = sub_end or reg_end

        # Mode - check 'mode' field
        mode_raw = str(item.get("mode", "")).upper()
        if mode_raw in ["ONLINE", "VIRTUAL"]:
            mode = HackathonMode.ONLINE
        elif mode_raw == "HYBRID":
            mode = HackathonMode.HYBRID
        elif mode_raw == "IN_PERSON":
            mode = HackathonMode.IN_PERSON
        else:
            mode = HackathonMode.UNKNOWN

        # Location - city/country fields
        city = item.get("city", "")
        country = item.get("country", "")
        venue = f"{city}, {country}".strip(", ") if city or country else ""

        # Tags
        flag = item.get("flag", "")
        tags = ["hack2skill"]
        if flag:
            tags.append(flag)
        participation = item.get("participation", "")
        if participation:
            tags.append(participation)

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            registration_deadline=reg_end,
            mode=mode,
            venue=venue,
            tags=tags,
            scraped_at=datetime.now(),
        )

    def _parse_iso_date(self, date_str: str) -> Optional[datetime]:
        """Parse ISO format dates from API"""
        if not date_str:
            return None
        try:
            # Handle format: "2026-04-10T04:30:00.000Z"
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            # Try parsing with microseconds
            return datetime.fromisoformat(date_str.replace("+00:00", ""))
        except (ValueError, AttributeError):
            return self._extract_date(date_str)