"""
Devnovate Scraper
API: https://devnovate.co/api/v1/events
"""

import logging
from typing import List, Optional
from datetime import datetime
import asyncio

import aiohttp

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class DevnovateScraper(BaseScraper):
    """Scraper for Devnovate hackathons"""

    source_name = SourceName.DEVNOVATE

    def _get_default_base_url(self) -> str:
        return "https://devnovate.co"

    def _get_default_search_paths(self) -> list:
        return ["/events"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape Devnovate API with retry"""
        hackathons = []

        try:
            session = await self._get_session()

            url = "https://devnovate.co/api/v1/events"

            # Retry logic (3 attempts)
            for attempt in range(3):
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            break
                        else:
                            self.logger.warning(f"Devnovate returned {response.status}")
                            if attempt < 2:
                                await asyncio.sleep(1)
                                continue
                            return []
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    self.logger.error(f"Devnovate scrape failed: {e}")
                    return []
            else:
                return []

            # Extract events
            events = []
            if isinstance(data, list):
                events = data
            elif isinstance(data, dict):
                events = data.get("data", []) or data.get("events", []) or data.get("results", [])

            for item in events:
                hackathon = self._parse_item(item)
                if hackathon:
                    hackathons.append(hackathon)

            self.logger.info(f"Scraped {len(hackathons)} from Devnovate")

        except Exception as e:
            self.logger.error(f"Devnovate scrape failed: {e}")

        finally:
            await self.close()

        return hackathons

    def _parse_item(self, item: dict) -> Optional[Hackathon]:
        """Parse a Devnovate item"""

        # Try multiple possible name fields
        name = (
            item.get("name") or 
            item.get("eventName") or 
            item.get("event_name") or
            item.get("title") or
            item.get("eventTitle") or
            ""
        )
        
        # Skip if name is empty or only whitespace
        if not name or not name.strip():
            return None
        
        # Clean up name - remove N/A placeholders, try other fields
        name = name.strip()
        name_upper = name.upper()
        if name_upper in ["N/A", "NA", "TBD", "TBA"]:
            # Fallback to subtitle or organizationName
            name = item.get("subtitle", "") or item.get("organizationName", "") or ""
            if not name.strip():
                # Even if name is N/A, check if we have valid slug - use slug as name
                slug = item.get("hackathon", "")
                if slug and slug.lower() not in ["na", "n/a", "tbd", "tba"]:
                    name = slug.replace("-", " ").title()
                else:
                    return None
            name = name.strip()
        
        # Handle slug for URL
        slug = item.get("hackathon", "")
        if slug:
            url = f"https://devnovate.co/event/{slug}"
        else:
            fallback_slug = item.get("eventName", "")
            if fallback_slug:
                url = f"https://devnovate.co/event/{fallback_slug}"
            else:
                url = "https://devnovate.co/events"

        # Mode - check status and location
        status = item.get("status", "").lower()
        location = item.get("location", "").lower()

        if status == "online" or location == "online":
            mode = HackathonMode.ONLINE
        elif "hybrid" in str(item.get("mode", "")).lower():
            mode = HackathonMode.HYBRID
        else:
            mode = HackathonMode.IN_PERSON

        # Dates
        start_date = self._parse_iso_date(item.get("startDate", ""))
        if not start_date:
            start_date = self._parse_date(item.get("startDate", ""))

        end_date = self._parse_iso_date(item.get("endDate", ""))
        if not end_date:
            end_date = self._parse_date(item.get("endDate", ""))

        reg_end = self._parse_iso_date(item.get("registrationDeadline", ""))
        if not reg_end:
            reg_end = self._parse_date(item.get("registrationDeadline", ""))

        # Clean venue - remove N/A values
        venue = item.get("location", "") or ""
        if venue.upper() in ["N/A", "NA", "TBD", "TBA"]:
            venue = ""

        # Clean prize pool - remove N/A values  
        prize = item.get("prizePool", "") or ""
        if prize.upper() in ["N/A", "NA", "TBD", "TBA"]:
            prize = ""

        # Tags - include theme
        tags = ["devnovate"]
        category = item.get("category", "")
        if category:
            tags.append(category)
        theme_list = item.get("theme", [])
        if theme_list:
            for t in theme_list[:3]:
                if t and t not in tags:
                    tags.append(t)

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            registration_deadline=reg_end,
            mode=mode,
            venue=venue,
            prize_pool=prize,
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
            return self._parse_date(date_str)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats"""
        if not date_str:
            return None

        date_str = date_str.strip()

        formats = [
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Try from iso format
        if len(date_str) > 10:
            try:
                return datetime.fromisoformat(date_str[:10])
            except:
                pass

        return self._extract_date(date_str)