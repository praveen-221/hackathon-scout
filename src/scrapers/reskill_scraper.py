"""
ReSkill Scraper
Go equivalent: src/go/pkg/fetcher/reskill.go
HTML scraping from reskilll.com/allhacks
"""

import logging
from typing import List, Optional
from datetime import datetime
from datetime import time as dt_module

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Hackathon, SourceName, HackathonMode

logger = logging.getLogger(__name__)


class ReSkillScraper(BaseScraper):
    """Scraper for ReSkill hackathons"""

    source_name = SourceName.RE_SKILL

    def _get_default_base_url(self) -> str:
        return "https://reskilll.com"

    def _get_default_search_paths(self) -> list:
        return ["/allhacks"]

    async def scrape(self) -> List[Hackathon]:
        """Scrape ReSkill hackathons"""
        hackathons = []

        try:
            session = await self._get_session()

            url = "https://reskilll.com/allhacks"

            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.warning(f"ReSkill returned {response.status}")
                    return []

                html = await response.text()

            soup = BeautifulSoup(html, "html.parser")

            # ReSkill uses a.allhackname class
            for link in soup.select("a.allhackname"):
                name = link.get_text(strip=True)
                if not name:
                    continue

                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = f"https://reskilll.com{href}"

                # Try to find registration date from parent
                end_date = None
                parent = link.parent
                while parent:
                    reg_head = parent.select_one(".hackregisterdatehead")
                    if reg_head and "Registration End" in reg_head.get_text():
                        next_elem = reg_head.find_next_sibling()
                        if next_elem:
                            date_text = next_elem.get_text(strip=True)
                            if date_text:
                                end_date = self._extract_date(date_text)
                        break
                    parent = parent.parent
                    if not parent:
                        break

                hackathons.append(Hackathon(
                    name=name[:200],
                    source=self.source_name,
                    url=href,
                    mode=HackathonMode.ONLINE,
                    end_date=end_date,
                    tags=["reskill"],
                    scraped_at=datetime.now(),
                ))

            self.logger.info(f"Scraped {len(hackathons)} from ReSkill")

        except Exception as e:
            self.logger.error(f"ReSkill scrape failed: {e}")

        finally:
            await self.close()

        return hackathons