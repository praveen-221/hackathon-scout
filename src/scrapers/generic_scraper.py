"""
Generic Scraper - single scraper that uses config-driven CSS selectors.
Replaces multiple site-specific scrapers.
"""

import logging
from typing import List, Optional
from datetime import datetime
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode


logger = logging.getLogger(__name__)


class GenericScraper(BaseScraper):
    """
    Generic scraper that uses CSS selectors from configuration.
    Supports both HTML scraping and API modes.
    """

    source_name = SourceName.UNKNOWN  # Set per-instance from config

    def __init__(self, config=None):
        super().__init__(config=config)
        self.session: Optional[aiohttp.ClientSession] = None

        # Extract CSS selectors from config (with empty fallback for safe attribute access)
        self.selector_card = getattr(config, "selector_card", "") if config else ""
        self.selector_title = getattr(config, "selector_title", "") if config else ""
        self.selector_link = getattr(config, "selector_link", "") if config else ""
        self.selector_date = getattr(config, "selector_date", "") if config else ""
        self.selector_mode = getattr(config, "selector_mode", "") if config else ""
        self.selector_desc = getattr(config, "selector_desc", "") if config else ""
        self.selector_tags = getattr(config, "selector_tags", "") if config else ""
        self.selector_prize = getattr(config, "selector_prize", "") if config else ""
        self.use_api = getattr(config, "use_api", False) if config else False
        self.api_url = getattr(config, "api_url", "") if config else ""
        self.api_response_format = (
            getattr(config, "api_response_format", "") if config else ""
        )

        # Pagination config
        self.per_page = getattr(config, "per_page", 20) if config else 20
        self.max_pages = getattr(config, "max_pages", 0) if config else 0  # 0 = unlimited
        self.page_param = getattr(config, "page_param", "page") if config else "page"
        self.per_page_param = getattr(config, "per_page_param", "per_page") if config else "per_page"

        # API headers and params
        self.api_headers = getattr(config, "api_headers", {}) if config else {}
        self.api_params = getattr(config, "api_params", {}) if config else {}

        # Set source name from config
        if config and config.name:
            try:
                self.source_name = SourceName(config.name)
            except ValueError:
                self.source_name = SourceName.UNKNOWN

    def _get_default_base_url(self) -> str:
        return ""

    def _get_default_search_paths(self) -> list:
        return ["/hackathons", "/events"]

    def _get_default_keywords(self) -> list:
        return ["hackathon"]

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            # Merge custom headers from config
            if self.api_headers:
                headers.update(self.api_headers)
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def scrape(self) -> List[Hackathon]:
        """Scrape using configured selectors or defaults"""
        hackathons = []

        try:
            session = await self._get_session()

            if self.use_api and self.api_url:
                # API mode
                hackathons = await self._scrape_api(session)
            else:
                # HTML mode - iterate over search paths
                for path in self.search_paths:
                    url = urljoin(self.base_url, path)
                    path_hackathons = await self._scrape_page(session, url)
                    hackathons.extend(path_hackathons)

        except Exception as e:
            self.logger.error(
                f"Error scraping {self.config.name if self.config else 'unknown'}: {e}"
            )

        finally:
            await self.close()

        self.logger.info(f"Scraped {len(hackathons)} hackathons")
        return hackathons

    async def _scrape_api(self, session: aiohttp.ClientSession) -> List[Hackathon]:
        """Scrape via API with configurable pagination support"""
        hackathons = []

        # Use full API URL directly from config
        base_api_url = self.api_url

        try:
            page = 1
            max_pages = None  # None means fetch until no more pages

            while True:
                # Build URL with pagination params
                api_url = self._build_paginated_url(base_api_url, page)
                self.logger.info(f"Fetching page {page}: {api_url}")

                # Build request headers
                request_headers = dict(session.headers)
                if self.api_headers:
                    request_headers.update(self.api_headers)

                async with session.get(api_url, headers=request_headers) as response:
                    if response.status != 200:
                        self.logger.warning(
                            f"API returned {response.status} for {api_url}"
                        )
                        break

                    try:
                        data = await response.json()
                    except Exception as e:
                        self.logger.error(f"Failed to parse JSON: {e}")
                        break

                    # Handle different API response formats
                    items = []

                    if self.api_response_format == "devpost":
                        # Devpost: {"hackathons": [...]}
                        items = data.get("hackathons", [])
                        # No pagination info in devpost - fetch single page
                        max_pages = page
                    elif self.api_response_format == "unstop":
                        # Unstop: {"data": {"data": [...], "current_page": 1, "last_page": 5, "total": 100}}
                        pagination_data = data.get("data", {})
                        items = pagination_data.get("data", [])

                        # Get pagination info from first response
                        if max_pages is None:
                            current_page = pagination_data.get("current_page", 1)
                            last_page = pagination_data.get("last_page", 1)
                            # Respect configured max_pages
                            if self.max_pages > 0:
                                max_pages = min(last_page, self.max_pages) if last_page > 0 else self.max_pages
                            else:
                                max_pages = last_page if last_page > 0 else 1
                            self.logger.info(
                                f"Pagination: page {current_page} of {max_pages}, per_page: {self.per_page}"
                            )
                    elif self.api_response_format == "devfolio":
                        # Devfolio: embedded JSON in HTML script
                        items = self._extract_devfolio_data(data)
                        max_pages = page  # Single page
                    elif self.api_response_format == "hack2skill":
                        # Hack2Skill: {"data": {"docs": [...]}}
                        docs = data.get("data", {}).get("docs", []) if isinstance(data.get("data", {}), dict) else data.get("data", [])
                        items = docs if isinstance(docs, list) else []
                        # Check for more pages
                        if max_pages is None:
                            total = data.get("data", {}).get("total", 0) if isinstance(data.get("data", {}), dict) else 0
                            if total > 0:
                                max_pages = (total + self.per_page - 1) // self.per_page
                            else:
                                max_pages = page
                    elif isinstance(data, list):
                        items = data
                        max_pages = page
                    else:
                        items = data.get("data", [])
                        # Check for generic pagination
                        if max_pages is None:
                            if "current_page" in data:
                                last_page = data.get("last_page", 1)
                                if self.max_pages > 0:
                                    max_pages = min(last_page, self.max_pages)
                                else:
                                    max_pages = last_page
                            elif "total" in data and "per_page" in data:
                                total = data.get("total", 0)
                                per_page = data.get("per_page", self.per_page)
                                max_pages = (total + per_page - 1) // per_page
                            else:
                                max_pages = 1

                # Parse items from this page
                for item in items:
                    hackathon = self._parse_api_item(item)
                    if hackathon:
                        hackathons.append(hackathon)

                self.logger.info(
                    f"Page {page}: got {len(items)} items, total: {len(hackathons)}"
                )

                # Check if we should continue to next page
                if max_pages is not None and page >= max_pages:
                    break

                # Check if we got fewer items than per_page (no more data)
                if self.max_pages == 0 and len(items) < self.per_page:
                    self.logger.info(f"Got {len(items)} items < per_page ({self.per_page}), stopping")
                    break

                page += 1

            self.logger.info(
                f"Total parsed {len(hackathons)} hackathons from {page} page(s)"
            )

        except Exception as e:
            self.logger.error(f"API scrape failed: {e}")

        return hackathons

    def _extract_devfolio_data(self, data: dict) -> list:
        """Extract hackathon data from Devfolio's embedded __NEXT_DATA__"""
        items = []
        try:
            # Devfolio embeds data in __NEXT_DATA__ script
            if "props" in data:
                page_props = data.get("props", {}).get("pageProps", {})
                dehydrated = page_props.get("dehydratedState", {})
                queries = dehydrated.get("queries", [])

                for query in queries:
                    state = query.get("state", {})
                    hackathons = state.get("data", {}).get("open_hackathons", [])
                    items.extend(hackathons)
        except Exception as e:
            self.logger.debug(f"Failed to extract Devfolio data: {e}")
        return items

    def _build_paginated_url(self, base_url: str, page: int) -> str:
        """Build URL with configurable pagination parameters"""
        from urllib.parse import urlparse, parse_qs, urlencode

        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query)

        # Add/update page parameter
        query_params[self.page_param] = [str(page)]

        # Add/update per_page parameter
        if self.per_page_param and self.per_page > 0:
            query_params[self.per_page_param] = [str(self.per_page)]

        # Add custom API params
        for key, value in self.api_params.items():
            if key not in query_params:
                query_params[key] = [value]

        # Reconstruct URL
        new_query = urlencode(query_params, doseq=True)
        new_url = parsed._replace(query=new_query).geturl()

        return new_url

    

    async def _scrape_page(
        self, session: aiohttp.ClientSession, url: str
    ) -> List[Hackathon]:
        """Scrape a single page"""
        hackathons = []

        try:
            self.logger.debug(f"Fetching {url}")
            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.warning(f"Got status {response.status} from {url}")
                    return []

                html = await response.text()

            if not html:
                self.logger.warning(f"Empty response from {url}")
                return []

            soup = BeautifulSoup(html, "html.parser")

            # Find cards using configured selector or fallbacks
            cards = []

            # Try configured selector
            if self.selector_card:
                cards = soup.select(self.selector_card)
                self.logger.debug(
                    f"Selector '{self.selector_card}' found {len(cards)} cards"
                )

            # Fallback: try common patterns
            if not cards:
                # Try common article/div patterns
                for fallback_selector in [
                    "article",
                    "div[class*='card']",
                    "div[class*='item']",
                    "li[class*='card']",
                    "div.hackathon",
                    ".challenge",
                ]:
                    cards = soup.select(fallback_selector)
                    if cards:
                        self.logger.debug(
                            f"Fallback selector '{fallback_selector}' found {len(cards)} cards"
                        )
                        break

            if not cards:
                self.logger.warning(f"No hackathon cards found on {url}")
                # Log some page structure for debugging
                self.logger.debug(
                    f"Page has {len(soup.find_all('a'))} links, {len(soup.find_all('article'))} articles"
                )
                return []

            for i, card in enumerate(cards):
                try:
                    hackathon = self._parse_card(card)
                    if hackathon:
                        hackathons.append(hackathon)
                    else:
                        self.logger.debug(
                            f"Card {i} parse returned None (no valid name/url)"
                        )
                except Exception as e:
                    self.logger.debug(f"Error parsing card {i}: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Page scrape failed for {url}: {e}")

        return hackathons

    def _parse_card(self, card: BeautifulSoup) -> Optional[Hackathon]:
        """Parse a card element using configured selectors with fallbacks"""

        # Title - try configured selector first, then fallbacks
        name = ""
        title_elem = None

        if self.selector_title:
            title_elem = card.select_one(self.selector_title)

        if not title_elem:
            # Fallback: look for headings or links with meaningful text
            for selector in ["h1", "h2", "h3", "h4", ".title", ".name", ".heading"]:
                title_elem = card.select_one(selector)
                if title_elem and title_elem.get_text(strip=True):
                    break

        if title_elem:
            name = title_elem.get_text(strip=True)

        # Link - try to find a link in the card
        url = ""

        if self.selector_link:
            link = card.select_one(self.selector_link)
            if link:
                url = link.get("href", "")

        if not url:
            # Fallback: find any link that looks like a hackathon link
            link = card.find("a", href=True)
            if link:
                href = link.get("href", "")
                # Prefer links with hackathon-related paths
                if any(
                    p in href.lower()
                    for p in ["hack", "challenge", "event", "competition"]
                ):
                    url = href
                elif href.startswith("http"):
                    url = href

        if not name or not url:
            # Last resort: try getting name from any heading and URL from any link
            heading = card.find(["h1", "h2", "h3", "h4"])
            if heading:
                name = heading.get_text(strip=True)
            link = card.find("a", href=True)
            if link:
                url = link.get("href", "")

        if not name or not url:
            return None

        # Full URL
        url = urljoin(self.base_url, url)

        # Date
        start_date = None
        end_date = None

        if self.selector_date:
            date_elem = card.select_one(self.selector_date)
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                start_date = self._extract_date(date_text)
                # Try to also extract end date from same text
                if " - " in date_text:
                    end_date = self._extract_date(date_text.split(" - ")[-1])

        if not start_date:
            # Fallback: look for any date-like text
            for selector in ["time", ".date", ".dates", "[datetime]"]:
                date_elem = card.select_one(selector)
                if date_elem:
                    start_date = self._extract_date(date_elem.get_text())
                    break

        # Mode
        mode = HackathonMode.UNKNOWN

        if self.selector_mode:
            mode_elem = card.select_one(self.selector_mode)
            if mode_elem:
                mode = self._extract_mode(mode_elem.get_text())

        if mode == HackathonMode.UNKNOWN:
            # Fallback: look for mode in card text
            card_text = card.get_text()
            mode = self._extract_mode(card_text)

        # Description
        description = ""

        if self.selector_desc:
            desc_elem = card.select_one(self.selector_desc)
            if desc_elem:
                description = self._clean_text(desc_elem.get_text())

        if not description:
            # Fallback: look for paragraph
            p = card.find("p")
            if p:
                description = self._clean_text(p.get_text())

        # Tags
        tags = []

        if self.selector_tags:
            tag_elems = card.select(self.selector_tags)
            tags = [t.get_text(strip=True) for t in tag_elems if t.get_text(strip=True)]

        if not tags:
            # Fallback: look for links that might be tags
            for selector in [".tag", ".tags", "a[href*='tag']", ".category"]:
                tag_elems = card.select(selector)
                if tag_elems:
                    tags = [
                        t.get_text(strip=True)
                        for t in tag_elems[:5]
                        if t.get_text(strip=True)
                    ]
                    break

        if not tags:
            tags = [self.config.name] if self.config else []

        # Prize
        prize = ""

        if self.selector_prize:
            prize_elem = card.select_one(self.selector_prize)
            if prize_elem:
                prize = prize_elem.get_text(strip=True)

        # Venue (for location info)
        venue = ""
        for selector in [".location", ".venue", ".address"]:
            loc = card.select_one(selector)
            if loc:
                venue = loc.get_text(strip=True)
                break

        return Hackathon(
            name=self._truncate(name, 200),
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            description=description,
            mode=mode,
            venue=venue,
            prize_pool=prize,
            tags=tags,
            scraped_at=datetime.now(),
        )

    def _parse_api_item(self, item: dict) -> Optional[Hackathon]:
        """Parse API response item based on response format"""

        # Parse based on format
        if self.api_response_format == "devpost":
            return self._parse_devpost_api(item)
        elif self.api_response_format == "unstop":
            return self._parse_unstop_api(item)
        elif self.api_response_format == "devfolio":
            return self._parse_devfolio_api(item)
        elif self.api_response_format == "hack2skill":
            return self._parse_hack2skill_api(item)
        else:
            # Default fallback
            return self._parse_generic_api(item)

    def _parse_devpost_api(self, item: dict) -> Optional[Hackathon]:
        """Parse Devpost API response"""

        name = item.get("title", "")
        if not name:
            return None

        url = item.get("url", "")
        if url and not url.startswith("http"):
            url = urljoin(self.base_url, url)

        # Devpost uses registration_end_date for deadline
        start_date = self._extract_date(item.get("start_date", ""))
        end_date = self._extract_date(item.get("registration_end_date", ""))

        # Devpost uses "mode" field directly
        mode_str = item.get("mode", "")
        mode = self._extract_mode(mode_str)

        # Description
        description = item.get("description", "")

        # Themes as tags
        themes = item.get("themes", [])
        tags = []
        if isinstance(themes, list):
            for theme in themes:
                if isinstance(theme, dict):
                    tags.append(theme.get("name", ""))
                else:
                    tags.append(str(theme))

        return Hackathon(
            name=self._truncate(name, 200),
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            description=description,
            mode=mode,
            prize_pool="",
            tags=tags,
            scraped_at=datetime.now(),
        )

    def _parse_unstop_api(self, item: dict) -> Optional[Hackathon]:
        """Parse Unstop API response"""

        name = item.get("title", "")
        if not name:
            return None

        # Unstop provides public_url (relative path)
        public_url = item.get("public_url", "")
        if public_url:
            url = urljoin(self.base_url, "/" + public_url)
        else:
            url = ""

        # Unstop dates
        start_date = self._extract_date(item.get("start_date", ""))
        end_date = self._extract_date(item.get("end_date", ""))

        # Unstop region field: "online" or "offline"
        region = item.get("region", "")
        if region == "online":
            mode = HackathonMode.ONLINE
        elif region == "offline":
            mode = HackathonMode.IN_PERSON
        else:
            mode = HackathonMode.UNKNOWN

        # Description (HTML)
        details = item.get("details", "")
        # Strip HTML tags for plain text
        description = self._clean_text(details) if details else ""

        # Tags from subtypes
        subtype = item.get("subtype", "")
        tags = [subtype] if subtype else []

        # Additional info
        prize = item.get("prize", "")
        organization = item.get("organization_name", "")

        return Hackathon(
            name=self._truncate(name, 200),
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            description=description[:500] if description else "",
            mode=mode,
            venue=organization,
            prize_pool=str(prize) if prize else "",
            tags=tags,
            scraped_at=datetime.now(),
        )

    def _parse_generic_api(self, item: dict) -> Optional[Hackathon]:
        """Parse generic API response"""

        name = item.get("title") or item.get("name") or ""
        if not name:
            return None

        url = item.get("url") or item.get("link") or ""
        if url and not url.startswith("http"):
            url = urljoin(self.base_url, url)

        # Dates
        start_date = self._extract_date(str(item.get("start_date", "")))
        end_date = self._extract_date(str(item.get("end_date", "")))

        # Mode
        mode = self._extract_mode(item.get("mode", ""))

        # Description
        description = item.get("description", "")

        # Tags
        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        if not tags:
            tags = [self.config.name] if self.config else []

        # Prize
        prize = item.get("prize") or item.get("prizes", "")

        return Hackathon(
            name=self._truncate(name, 200),
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            description=description,
            mode=mode,
            prize_pool=prize,
            tags=tags,
            scraped_at=datetime.now(),
        )

    def _parse_devfolio_api(self, item: dict) -> Optional[Hackathon]:
        """Parse Devfolio API response (embedded in HTML)"""

        name = item.get("name", "")
        if not name:
            return None

        slug = item.get("slug", "")
        url = f"https://{slug}.devfolio.co" if slug else ""

        # Dates in RFC3339
        start_date = self._extract_date(item.get("starts_at", ""))
        end_date = self._extract_date(item.get("ends_at", ""))

        # Mode
        is_online = item.get("is_online", False)
        mode = HackathonMode.ONLINE if is_online else HackathonMode.IN_PERSON

        # Location
        venue = item.get("location", "")

        return Hackathon(
            name=self._truncate(name, 200),
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            description="",
            mode=mode,
            venue=venue,
            tags=[self.source_name.value] if self.source_name else [],
            scraped_at=datetime.now(),
        )

    def _parse_hack2skill_api(self, item: dict) -> Optional[Hackathon]:
        """Parse Hack2Skill API response"""

        name = item.get("title", "")
        if not name:
            return None

        # Get event URL/slug
        slug = item.get("eventUrl", "") or item.get("slug", "") or item.get("event_slug", "")
        event_id = item.get("id") or item.get("_id", "")

        if slug:
            url = f"https://vision.hack2skill.com/event/{slug}"
        elif event_id:
            url = f"https://vision.hack2skill.com/event/{event_id}"
        else:
            url = ""

        # Dates - check multiple fields
        parse_time = lambda v: self._extract_date(str(v)) if v else None

        sub_start = parse_time(item.get("submissionStart"))
        sub_end = parse_time(item.get("submissionEnd"))
        reg_start = parse_time(item.get("registrationStart"))
        reg_end = parse_time(item.get("registrationEnd"))

        start_date = sub_start or reg_start
        end_date = sub_end or reg_end

        # Mode
        mode_raw = item.get("mode", "")
        if mode_raw.lower() in ["online", "virtual"]:
            mode = HackathonMode.ONLINE
        elif mode_raw.lower() == "hybrid":
            mode = HackathonMode.HYBRID
        else:
            mode = HackathonMode.IN_PERSON

        # Location
        city = item.get("city", "")
        country = item.get("country", "")
        venue = f"{city}, {country}".strip(", ") if city or country else ""

        # Registration deadline
        registration_deadline = reg_end

        return Hackathon(
            name=self._truncate(name, 200),
            source=self.source_name,
            url=url,
            start_date=start_date,
            end_date=end_date,
            registration_deadline=registration_deadline,
            description="",
            mode=mode,
            venue=venue,
            tags=[self.source_name.value] if self.source_name else [],
            scraped_at=datetime.now(),
        )
