"""
Storage manager for hackathon data
Handles persistence and deduplication
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

from .models import Hackathon


logger = logging.getLogger(__name__)


class StorageManager:
    """Manages hackathon data storage and deduplication"""

    def __init__(self, file_path: str, dedup_days: int = 30, max_entries: int = 500, unfiltered_file_path: str = None, store_unfiltered: bool = False):
        self.file_path = file_path
        self.dedup_days = dedup_days
        self.max_entries = max_entries
        self.unfiltered_file_path = unfiltered_file_path
        self.store_unfiltered = store_unfiltered
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """Create storage directory if it doesn't exist"""
        dir_path = os.path.dirname(self.file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def load(self) -> List[Hackathon]:
        """Load hackathons from storage"""
        if not os.path.exists(self.file_path):
            return []

        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)

            hackathons = [Hackathon.from_dict(item) for item in data]
            logger.info(f"Loaded {len(hackathons)} hackathons from storage")
            return hackathons
        except Exception as e:
            logger.error(f"Error loading storage: {e}")
            return []

    def save(self, hackathons: List[Hackathon]):
        """Save hackathons to storage"""
        try:
            # Filter out invalid entries before saving
            valid_hackathons = []
            for h in hackathons:
                name_check = h.name.upper().strip() if h.name else ""
                if name_check in ["N/A", "NA", "TBD", "TBA", "AN/", "N/A ", ""]:
                    continue
                valid_hackathons.append(h)
            
            data = [h.to_dict() for h in valid_hackathons if h.to_dict() is not None]
            with open(self.file_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(hackathons)} hackathons to storage")
        except Exception as e:
            logger.error(f"Error saving storage: {e}")

    def save_unfiltered(self, hackathons: List[Hackathon]):
        """Save all scraped hackathons (before filtering) to separate storage"""
        if not self.store_unfiltered or not self.unfiltered_file_path:
            return
        try:
            data = [h.to_dict() for h in hackathons]
            # Ensure directory exists
            dir_path = os.path.dirname(self.unfiltered_file_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(self.unfiltered_file_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(hackathons)} unfiltered hackathons to {self.unfiltered_file_path}")
        except Exception as e:
            logger.error(f"Error saving unfiltered storage: {e}")

    def merge_new_hackathons(
        self, new_hackathons: List[Hackathon]
    ) -> tuple[List[Hackathon], List[Hackathon]]:
        """
        Merge new hackathons with existing ones.
        Returns: (all_hackathons, new_hackathons_only)
        """
        existing = self.load()
        existing_keys = {h.unique_key() for h in existing}

        # Filter out duplicates
        truly_new = []
        for h in new_hackathons:
            if h.unique_key() not in existing_keys:
                truly_new.append(h)
            else:
                logger.debug(f"Skipping duplicate: {h.name}")

        logger.info(
            f"Found {len(truly_new)} new hackathons out of {len(new_hackathons)} scraped"
        )

        # Combine and limit
        all_hackathons = truly_new + existing
        if len(all_hackathons) > self.max_entries:
            all_hackathons = all_hackathons[: self.max_entries]

        self.save(all_hackathons)

        return all_hackathons, truly_new

    def get_recent_hackathons(self, days: int = 30) -> List[Hackathon]:
        """Get hackathons scraped within the last N days"""
        all_hackathons = self.load()
        cutoff = datetime.now() - timedelta(days=days)

        recent = [h for h in all_hackathons if h.scraped_at >= cutoff]
        return recent

    def get_hackathons_by_key(self, unique_keys: List[str]) -> List[Hackathon]:
        """Get hackathons by their unique keys"""
        all_hackathons = self.load()
        key_set = set(unique_keys)

        return [h for h in all_hackathons if h.unique_key() in key_set]

    def clear_old_entries(self, days: int = 90):
        """Remove hackathons older than N days"""
        all_hackathons = self.load()
        cutoff = datetime.now() - timedelta(days=days)

        filtered = [h for h in all_hackathons if h.scraped_at >= cutoff]

        if len(filtered) < len(all_hackathons):
            self.save(filtered)
            logger.info(f"Cleared {len(all_hackathons) - len(filtered)} old entries")

        return filtered
