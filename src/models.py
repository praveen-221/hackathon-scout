"""
Data models for Hackathon information
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


class HackathonMode(str, Enum):
    ONLINE = "online"
    IN_PERSON = "in-person"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class SourceName(str, Enum):
    DEVPOST = "devpost"
    HACKATHON_IO = "hackathon_io"
    HACK2SKILL_VISION = "hack2skill_vision"
    MLH = "mlh"
    TECHCRUNCH = "techcrunch"
    HACK2SKILL = "hack2skill"
    UNSTOP = "unstop"
    DEVFOLIO = "devfolio"
    RE_SKILL = "reskill"
    WHEREUELEVATE = "whereuelevate"
    HACKEREARTH = "hackerearth"
    DEVNOVATE = "devnovate"
    UNKNOWN = "unknown"


@dataclass
class Hackathon:
    """Unified hackathon data model"""

    name: str
    source: SourceName
    url: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    description: str = ""
    mode: HackathonMode = HackathonMode.UNKNOWN
    venue: str = ""
    participation_criteria: str = ""
    prize_pool: str = ""
    tags: List[str] = field(default_factory=list)
    scraped_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source.value,
            "url": self.url,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "registration_deadline": self.registration_deadline.isoformat()
            if self.registration_deadline
            else None,
            "description": self.description[:500] if self.description else "",
            "mode": self.mode.value,
            "venue": self.venue,
            "participation_criteria": self.participation_criteria,
            "prize_pool": self.prize_pool,
            "tags": self.tags,
            "scraped_at": self.scraped_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Hackathon":
        return cls(
            name=data.get("name", ""),
            source=SourceName(data.get("source", "unknown")),
            url=data.get("url", ""),
            start_date=datetime.fromisoformat(data["start_date"])
            if data.get("start_date")
            else None,
            end_date=datetime.fromisoformat(data["end_date"])
            if data.get("end_date")
            else None,
            registration_deadline=datetime.fromisoformat(data["registration_deadline"])
            if data.get("registration_deadline")
            else None,
            description=data.get("description", ""),
            mode=HackathonMode(data.get("mode", "unknown")),
            venue=data.get("venue", ""),
            participation_criteria=data.get("participation_criteria", ""),
            prize_pool=data.get("prize_pool", ""),
            tags=data.get("tags", []),
            scraped_at=datetime.fromisoformat(data["scraped_at"])
            if data.get("scraped_at")
            else datetime.now(),
        )

    def matches_fields(
        self, target_fields: List[str], keyword_expansions: Dict[str, List[str]] = None
    ) -> bool:
        """
        Check if hackathon matches any of the target fields.
        Uses flexible keyword matching - fields act as search keywords.

        Args:
            target_fields: List of field names to match against
            keyword_expansions: Optional dict mapping field names to expanded keywords
        """
        if not target_fields:
            return True

        # Build search text from all relevant fields
        search_text = " ".join(
            [
                self.name,
                self.description,
                " ".join(self.tags),
                self.venue,
                self.participation_criteria,
            ]
        ).lower()

        # Build keyword set from fields with configurable expansions
        field_keywords = set()

        for field in target_fields:
            field_lower = field.lower()

            # First try config expansions (if provided)
            if keyword_expansions:
                if field_lower in keyword_expansions:
                    field_keywords.update(keyword_expansions[field_lower])
                else:
                    # Partial match
                    for key, values in keyword_expansions.items():
                        if key in field_lower or field_lower in key:
                            field_keywords.update(values)
                            break

            # Fall back to extracting terms from field name
            if not field_keywords:
                terms = (
                    field_lower.replace("/", " ")
                    .replace("-", " ")
                    .replace("_", " ")
                    .split()
                )
                field_keywords.update(terms)

        # Check if any keyword matches
        for keyword in field_keywords:
            if keyword and keyword in search_text:
                return True

        return False

    def is_within_date_range(self, min_days: int, max_days: int) -> bool:
        # If filter is disabled (0, None, or both same), pass through
        if min_days is None and max_days is None:
            return True
        if min_days == 0 and max_days == 0:
            return True
        # No start date - treat as unknown, pass through
        if not self.start_date:
            return True
        today = datetime.now()
        days_until = (self.start_date - today).days
        return min_days <= days_until <= max_days

    def matches_eligibility(self, keywords: List[str], mode: str = "exclude") -> bool:
        """
        Check if hackathon eligibility criteria matches based on mode.

        Args:
            keywords: List of keywords to check
            mode: "include" or "exclude"
              - "exclude": return False if any keyword matches (filter OUT matches)
              - "include": return True only if any keyword matches (keep ONLY matches)

        Returns:
            True if should be included, False otherwise
        """
        # No keywords specified - include all
        if not keywords:
            return True

        # No participation criteria
        if not self.participation_criteria:
            # If mode is exclude (filtering OUT): if no criteria, we can't filter, include it
            # If mode is include (keeping ONLY): if no criteria, can't match, exclude it
            return mode == "exclude"

        criteria_lower = self.participation_criteria.lower()
        has_match = any(keyword.lower() in criteria_lower for keyword in keywords)

        if mode == "exclude":
            # Exclude mode: filter OUT items that match - return False if match found
            return not has_match
        else:
            # Include mode: keep ONLY items that match - return True only if match found
            return has_match

    def matches_regions(self, regions: List[str]) -> bool:
        """
        Check if hackathon matches the specified regions.
        Only applies to in-person and hybrid events.
        Online events always pass this filter.

        Args:
            regions: List of countries/regions to filter for

        Returns:
            True if hackathon should be included, False otherwise
        """
        # No regions specified - include all
        if not regions:
            return True

        # Online events are not filtered by region
        if self.mode == HackathonMode.ONLINE:
            return True

        # For in-person/hybrid, check if venue matches any region
        search_text = " ".join([self.venue, self.description]).lower()

        for region in regions:
            region_lower = region.lower()
            if region_lower in search_text:
                return True

        # No match found - filter out
        return False

    def unique_key(self) -> str:
        return f"{self.name.lower().strip()}_{self.source.value}"

    def is_india_specific(self) -> bool:
        """
        Check if hackathon is India-specific.
        Matches Go's IsIndiaSpecific() implementation.

        Returns True if:
        - Country is "India"
        - Venue is in an Indian city
        - Mode is "online" (online events include India)
        """
        # Check explicit country
        venue_text = f"{self.venue} {self.description}".lower()

        indian_cities = [
            "bangalore", "bengaluru", "delhi", "mumbai", "pune", "hyderabad",
            "chennai", "gurgaon", "gurugram", "noida", "kolkata", "ahmedabad",
            "jaipur", "indore", "chandigarh", "coimbatore", "kochi", "trivandrum",
        ]

        # Check if venue contains any Indian city name
        for city in indian_cities:
            if city in venue_text:
                return True

        # Check if online (online events include India by default)
        if self.mode == HackathonMode.ONLINE:
            return True

        return False
