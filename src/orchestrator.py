"""
Main scraper orchestrator
Coordinates scraping, storage, and notification
"""

import asyncio
import logging
import logging.handlers
import os
import sys
from typing import List, Tuple
from datetime import datetime

from .config import ConfigManager, Config
from .models import Hackathon, SourceName, HackathonMode
from .storage import StorageManager
from .scrapers import ScraperFactory
from .emailer import EmailNotifier


logger = logging.getLogger(__name__)


class HackathonScraper:
    """Main orchestrator for hackathon scraping"""

    def __init__(self, config_path: str = None):
        self.config_mgr = ConfigManager(config_path)
        self.config: Config = None
        self.storage: StorageManager = None
        self.emailer: EmailNotifier = None

    def setup_logging(self):
        """Configure logging"""
        self.config = self.config_mgr.config

        # Ensure log directory exists
        log_file = self.config.logging.file
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Create logger
        log_level = getattr(logging, self.config.logging.level.upper(), logging.INFO)

        handlers = []

        # File handler with rotation
        if log_file:
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=self.config.logging.max_size_mb * 1024 * 1024,
                    backupCount=self.config.logging.backup_count,
                )
            )

        # Console handler
        if self.config.logging.console:
            handlers.append(logging.StreamHandler(sys.stdout))

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=handlers,
        )

        logger.info("Logging configured")

    def _is_valid_hackathon(self, h: Hackathon) -> bool:
        """Check if hackathon has valid name (not N/A, TBD, etc.)"""
        if not h.name:
            return False
        name_check = h.name.upper().strip()
        return name_check not in ["N/A", "NA", "TBD", "TBA", "AN/", ""]

    def setup_storage(self):
        """Initialize storage manager"""
        self.storage = StorageManager(
            file_path=self.config.storage.file_path,
            dedup_days=self.config.storage.dedup_days,
            max_entries=self.config.storage.max_entries,
            unfiltered_file_path=self.config.storage.unfiltered_file_path,
            store_unfiltered=self.config.storage.store_unfiltered,
        )
        logger.info("Storage initialized")

    def setup_emailer(self) -> bool:
        """Initialize email notifier"""
        if not self.config.email:
            logger.warning("Email not configured - skipping email notifications")
            return False

        if not self.config.email.recipient_list:
            logger.warning("No email recipients configured - skipping")
            return False

        if not self.config.email.sender_password:
            logger.warning("No email password configured - skipping")
            return False

        self.emailer = EmailNotifier(
            smtp_host=self.config.email.smtp_host,
            smtp_port=self.config.email.smtp_port,
            sender_email=self.config.email.sender_email,
            password=self.config.email.sender_password,
            recipients=self.config.email.recipient_list,
            use_tls=self.config.email.use_tls,
            subject_prefix=self.config.email.subject_prefix,
        )

        logger.info(
            f"Email notifier configured for {len(self.config.email.recipient_list)} recipients"
        )
        return True

    async def scrape_all_sources(self) -> List[Hackathon]:
        """Scrape from all enabled sources"""
        all_hackathons = []

        # Get enabled sources sorted by priority
        enabled_sources = [s for s in self.config.sources if s.enabled]
        enabled_sources.sort(key=lambda x: x.priority)

        logger.info(
            f"Scraping from {len(enabled_sources)} sources: {[s.name for s in enabled_sources]}"
        )

        for source in enabled_sources:
            scraper = ScraperFactory.create(source.name, config=source)

            if not scraper:
                logger.warning(f"Scraper not available: {source.name}")
                continue

            logger.info(f"Scraping {source.name}...")

            try:
                hackathons = await scraper.scrape()
                all_hackathons.extend(hackathons)
                logger.info(f"  -> Got {len(hackathons)} hackathons from {source.name}")
            except Exception as e:
                logger.error(f"Error scraping {source.name}: {e}")

        # Also add MLH if enabled (for demo purposes)
        mlh_source = next((s for s in enabled_sources if s.name == "mlh"), None)
        if mlh_source:
            # Add sample MLH hackathons for demonstration
            sample_mlh = self._get_sample_mlh_hackathons()
            all_hackathons.extend(sample_mlh)

        return all_hackathons

    def _get_sample_mlh_hackathons(self) -> List[Hackathon]:
        """Get sample MLH hackathons for demonstration"""
        # In production, this would be a real MLH scraper
        return [
            Hackathon(
                name="MLH Spring Fellowship Hackathon",
                source=SourceName.MLH,
                url="https://fellowship.mlh.io/",
                start_date=datetime(2026, 5, 1),
                end_date=datetime(2026, 5, 3),
                mode=HackathonMode.ONLINE,
                description="Virtual hackathon for MLH Fellows. Build projects, learn, and connect with the community.",
                tags=["MLH", "Fellowship", "Virtual"],
                participation_criteria="Open to MLH Fellowship applicants",
            ),
            Hackathon(
                name="Local Hack Day: Build Day",
                source=SourceName.MLH,
                url="https://localhackday.mlh.io/",
                start_date=datetime(2026, 4, 20),
                end_date=datetime(2026, 4, 20),
                mode=HackathonMode.HYBRID,
                description="A global day of building. Join thousands of developers worldwide for a day of coding.",
                tags=["MLH", "Global", "One-day"],
                participation_criteria="Open to all developers",
            ),
        ]

    def filter_hackathons(self, hackathons: List[Hackathon]) -> List[Hackathon]:
        """Filter hackathons based on config"""
        # Get keyword expansions from config
        keyword_expansions = {}
        if self.config.keywords_expand and self.config.keywords_expand.expansions:
            keyword_expansions = self.config.keywords_expand.expansions

        # Get regions filter
        regions = self.config.filters.regions if self.config.filters else []

        # Get India filter
        india_only = self.config.filters.india_only if self.config.filters else False

        filtered = []

        for h in hackathons:
            # Filter by fields/topics with configurable keyword expansions
            if not h.matches_fields(self.config.fields, keyword_expansions):
                continue

            # Filter by date range
            if not h.is_within_date_range(
                self.config.filters.min_days_ahead, self.config.filters.max_days_ahead
            ):
                continue

            # Filter by region (only for in-person/hybrid events)
            if not h.matches_regions(regions):
                continue

            # Filter by India-specific (matches Go's IsIndiaSpecific)
            if india_only and not h.is_india_specific():
                continue

            # Filter by eligibility criteria
            eligibility_keywords = self.config.filters.eligibility_keywords if self.config.filters else []
            eligibility_mode = self.config.filters.eligibility_mode if self.config.filters else "exclude"
            if not h.matches_eligibility(eligibility_keywords, eligibility_mode):
                continue

            filtered.append(h)

        logger.info(f"Filtered to {len(filtered)} hackathons matching criteria")
        return filtered

    async def run(self) -> Tuple[int, int]:
        """
        Run the full scraping pipeline

        Returns:
            Tuple of (total_scraped, new_count)
        """
        logger.info("=" * 50)
        logger.info("Hackathon Scout Starting")
        logger.info("=" * 50)

        # Load config
        self.config = self.config_mgr.load()
        logger.info(
            f"Loaded config: {len(self.config.fields)} fields, {len(self.config.sources)} sources"
        )

        # Setup
        self.setup_logging()
        self.setup_storage()
        email_enabled = self.setup_emailer()

        start_time = datetime.now()

        # Scrape
        logger.info("Starting scrape...")
        all_hackathons = await self.scrape_all_sources()

        # Save unfiltered data before filtering
        if self.storage.store_unfiltered:
            logger.info(f"Saving {len(all_hackathons)} unfiltered hackathons...")
            self.storage.save_unfiltered(all_hackathons)

        # Filter
        logger.info("Filtering hackathons...")
        filtered = self.filter_hackathons(all_hackathons)

        # Store and deduplicate
        logger.info("Storing and deduplicating...")
        
        # Filter out invalid entries (N/A, TBD, etc.) before storing/emailing
        valid_new = [h for h in filtered if self._is_valid_hackathon(h)]
        logger.info(f"Filtered to {len(valid_new)} valid hackathons after removing invalid entries")
        
        all_hackathons, valid_for_email = self.storage.merge_new_hackathons(valid_new)

        # Send email if configured
        if email_enabled and valid_for_email:
            logger.info(f"Sending email for {len(valid_for_email)} new hackathons...")
            success = self.emailer.send(valid_for_email)
            if success:
                logger.info("Email sent successfully")
            else:
                logger.error("Failed to send email")

        # Cleanup old entries
        self.storage.clear_old_entries(90)

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info("=" * 50)
        logger.info(f"Completed in {elapsed:.1f}s")
        logger.info(f"Total hackathons: {len(all_hackathons)}")
        logger.info(f"New this run: {len(valid_for_email)}")
        logger.info("=" * 50)

        return len(all_hackathons), len(valid_for_email)


async def main():
    """Main entry point"""
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")

    scraper = HackathonScraper(config_path)

    try:
        total, new = await scraper.run()

        # Exit with appropriate code
        if new > 0:
            sys.exit(0)  # Found new hackathons
        else:
            sys.exit(0)  # No new hackathons (not an error)

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
