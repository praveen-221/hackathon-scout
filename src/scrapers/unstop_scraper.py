"""
Unstop Scraper
Go equivalent: src/go/pkg/fetcher/unstop.go
API: https://unstop.com/api/public/opportunity/search-result
"""

import logging
from typing import List, Optional
from datetime import datetime
from urllib.parse import urljoin

import aiohttp

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class UnstopScraper(BaseScraper):
    """Scraper for Unstop hackathons"""

    source_name = SourceName.UNSTOP

    def _get_default_base_url(self) -> str:
        return "https://unstop.com"

    def _get_default_search_paths(self) -> list:
        return ["/hackathons"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape Unstop API with pagination"""
        hackathons = []

        try:
            session = await self._get_session()

            base_url = "https://unstop.com/api/public/opportunity/search-result"
            params = "opportunity=hackathons&oppstatus=open"
            per_page = 200
            page = 1

            while True:
                url = f"{base_url}?{params}&page={page}&per_page={per_page}"
                self.logger.debug(f"Fetching page {page}: {url}")

                async with session.get(url) as response:
                    if response.status != 200:
                        self.logger.warning(f"Unstop returned {response.status}")
                        break

                    data = await response.json()

                # Unstop: {"data": {"data": [...], "current_page": 1, "last_page": 5}}
                pagination_data = data.get("data", {})
                items = pagination_data.get("data", [])

                for item in items:
                    hackathon = self._parse_item(item)
                    if hackathon:
                        hackathons.append(hackathon)

                # Check pagination
                current_page = pagination_data.get("current_page", 1)
                last_page = pagination_data.get("last_page", 1)

                self.logger.debug(f"Page {current_page} of {last_page}: got {len(items)} items")

                if current_page >= last_page:
                    break

                page += 1

            self.logger.info(f"Scraped {len(hackathons)} from Unstop")

        except Exception as e:
            self.logger.error(f"Unstop scrape failed: {e}")

        finally:
            await self.close()

        return hackathons

    def _parse_item(self, item: dict) -> Optional[Hackathon]:
        """Parse an Unstop hackathon item"""

        name = item.get("title", "")
        if not name:
            return None

        # URL
        public_url = item.get("public_url", "")
        if public_url:
            url = urljoin(self.base_url, "/" + public_url)
        else:
            url = ""

        # Dates - check multiple sources
        # 1. Direct end_date
        start_date = None
        end_date = self._extract_date(item.get("end_date", ""))

        # 2. Festival dates (for college fests)
        festival = item.get("festival", {})
        if festival:
            fest_start = festival.get("start_date", "")
            fest_end = festival.get("end_date", "")
            if fest_start:
                start_date = self._extract_date(fest_start)
            if fest_end:
                end_date = self._extract_date(fest_end)

        # 3. Use start_date if no start date found
        if not start_date:
            start_date = self._extract_date(item.get("start_date", ""))

        # Eligibility criteria from regnRequirements
        participation_criteria = ""
        eligibility = None

        # 4. Extract from description if still no dates
        details = item.get("details", "")
        if details and (not start_date or not end_date):
            desc_dates = self._extract_dates_from_html(details)
            if not start_date and desc_dates[0]:
                start_date = desc_dates[0]
            if not end_date and desc_dates[1]:
                end_date = desc_dates[1]

        # Registration deadline
        regn = item.get("regnRequirements", {})
        if regn:
            reg_end = regn.get("end_regn_dt", "")
            if reg_end and not end_date:
                end_date = self._extract_date(reg_end)
            eligibility = regn.get("eligibility", "")
            if eligibility and not participation_criteria:
                participation_criteria = self._clean_text(str(eligibility))

        # Mode
        region = item.get("region", "")
        if region == "online":
            mode = HackathonMode.ONLINE
        elif region == "offline":
            mode = HackathonMode.IN_PERSON
        else:
            mode = HackathonMode.UNKNOWN

        # Description - clean HTML and truncate
        details = item.get("details", "")
        description = self._clean_text(details)[:500] if details else ""

        # Prize - extract prizes list
        prizes = item.get("prizes", [])
        prize_str = ""
        if prizes:
            prize_parts = []
            for p in prizes[:3]:  # Top 3 prizes
                rank = p.get("rank", "")
                cash = p.get("cash")
                if cash:
                    prize_parts.append(f"{rank}: ${cash}")
                elif p.get("certificate"):
                    if rank:
                        prize_parts.append(f"{rank}: Certificate")
            prize_str = ", ".join(prize_parts)

        # Tags - from required_skills and workfunction
        tags = ["unstop"]
        for skill in item.get("required_skills", [])[:5]:
            skill_name = skill.get("skill_name", "")
            if skill_name:
                tags.append(skill_name)
        subtype = item.get("subtype", "")
        if subtype and subtype not in tags:
            tags.append(subtype)

        # Venue from address
        venue = ""
        address = item.get("address_with_country_logo", {})
        if address:
            addr_parts = []
            city = address.get("city", "")
            state = address.get("state", "")
            country = address.get("country", {})
            if city:
                addr_parts.append(city)
            if state:
                addr_parts.append(state)
            if country and isinstance(country, dict):
                country_name = country.get("name", "")
                if country_name:
                    addr_parts.append(country_name)
            if addr_parts:
                venue = ", ".join(addr_parts)

        # Organization
        org = item.get("organisation", {})
        org_name = org.get("name", "") if org else ""
        if org_name and not description:
            description = f"Organized by {org_name}"

        return Hackathon(
            name=name[:200],
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            description=description,
            mode=mode,
            venue=venue,
            participation_criteria=participation_criteria[:500] if participation_criteria else "",
            prize_pool=prize_str,
            tags=tags,
            scraped_at=datetime.now(),
        )

    def _extract_dates_from_html(self, html: str) -> tuple:
        """Extract dates from HTML description like 'Date: 25 April 2026' or 'Registration Deadline: 20th April, 2026'"""
        import re
        start_date = None
        end_date = None

        if not html:
            return start_date, end_date

        # Clean HTML tags and decode entities
        text = re.sub(r'<[^>]+>', ' ', html)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&rsquo;', "'").replace('&lsquo;', "'").replace('&ndash;', '-').replace('&ldquo;', '"').replace('&rdquo;', '"')

        # Remove ordinal suffixes: 20th, 1st, 2nd, 3rd, 4th etc
        text = re.sub(r'(\d+)(st|nd|rd|th)\b', r'\1', text, flags=re.IGNORECASE)

        # Find patterns like "Date: 25 April 2026" or "Registration Deadline: 20 April, 2026"
        # Also handle "April 20, 2026" or "20 April"
        date_patterns = [
            # Full date with day, month, year
            r'Date:\s*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(\d{4})',
            r'Registration\s*Deadline[:\s]*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(\d{4})',
            r'Deadline[:\s]*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(\d{4})',
            r'Deadline[:\s]*\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s*,?\s*(\d{4})',
            r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(\d{4})',
            # Month day, year format (e.g., "April 20, 2026" or "April 20th, 2026")
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s*,?\s*(\d{4})',
            # Date range formats
            r'Date[:\s]*(\d{1,2})-(\d{1,2})-(\d{4})',
            r'(\d{1,2})-(\d{1,2})-(\d{4})',
            # Just a standalone date like "21st April, 2026" or "April 21, 2026" - more flexible
            r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b\s*,?\s*(\d{4})',
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\b\s*,?\s*(\d{4})',
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 3:
                    # Handle date range format like "25-04-2026"
                    if '-' in match[0] and '-' in match[1]:
                        try:
                            parsed = datetime.strptime(f"{match[0]}-{match[1]}-{match[2]}", "%d-%m-%Y")
                            if not start_date:
                                start_date = parsed
                            elif not end_date:
                                end_date = parsed
                        except ValueError:
                            continue
                    # Handle "Month Day, Year" format (e.g., "April 20, 2026")
                    elif match[0].lower() in ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']:
                        try:
                            parsed = datetime.strptime(f"{match[0]} {match[1]} {match[2]}", "%B %d %Y")
                            if not start_date:
                                start_date = parsed
                            elif not end_date:
                                end_date = parsed
                        except ValueError:
                            continue
                    else:
                        day, month, year = match
                        try:
                            parsed = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
                            if not start_date:
                                start_date = parsed
                            elif not end_date:
                                end_date = parsed
                        except ValueError:
                            continue

        return start_date, end_date