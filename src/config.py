"""
Configuration Manager for Hackathon Scout
Loads and validates YAML configuration
"""

import os
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pathlib import Path


# Pattern to match ${VARIABLE_NAME} in config values
ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_env_var(value: str) -> str:
    """Resolve ${VARIABLE_NAME} pattern from environment variables"""
    if not isinstance(value, str):
        return value

    def replacer(match):
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable {var_name} is not set")
        return env_value

    return ENV_VAR_PATTERN.sub(replacer, value)


def parse_recipient_list(value: str | list) -> List[str]:
    """Parse recipient list from comma-separated string or list"""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Split by comma and strip whitespace
        return [email.strip() for email in value.split(",") if email.strip()]
    return []


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    sender_email: str
    sender_password: str  # Name of env var
    recipient_list: List[str] = field(default_factory=list)
    use_tls: bool = True
    subject_prefix: str = "[Hackathon Scout]"


@dataclass
class SourceConfig:
    name: str
    enabled: bool = True
    priority: int = 1
    base_url: str = ""  # Base URL for scraping
    search_paths: List[str] = field(
        default_factory=list
    )  # URL paths to search (e.g., /hackathons, /events)
    keywords: List[str] = field(default_factory=list)  # Keywords to search within page

    # CSS selectors for scraping (generic scraper uses these)
    selector_card: str = ""  # Selector for hackathon card/item
    selector_title: str = ""  # Selector for title element
    selector_link: str = ""  # Selector for link (within title or separate)
    selector_date: str = ""  # Selector for date element
    selector_mode: str = ""  # Selector for mode/location
    selector_desc: str = ""  # Selector for description
    selector_tags: str = ""  # Selector for tags
    selector_prize: str = ""  # Selector for prize/pool

    # API settings (optional - set to use API instead of HTML)
    use_api: bool = False
    api_url: str = ""  # Full API URL (e.g., "https://devpost.com/api/hackathons")
    api_response_format: str = ""  # Format of API response: "devpost", "unstop", etc.

    # Pagination settings for API endpoints
    per_page: int = 100  # Number of results per page
    max_pages: int = 0  # Maximum pages to fetch (0 = unlimited until no more)
    page_param: str = "page"  # URL param name for page number
    per_page_param: str = "per_page"  # URL param name for per_page

    # Custom API headers (e.g., for authentication)
    api_headers: Dict[str, str] = field(default_factory=dict)

    # Additional API parameters (e.g., status filters)
    api_params: Dict[str, str] = field(default_factory=dict)


@dataclass
class FiltersConfig:
    min_days_ahead: int = 0
    max_days_ahead: int = 180
    include_ended: bool = False
    regions: List[str] = field(
        default_factory=list
    )  # Countries/regions for in-person events
    india_only: bool = False  # Filter to India-specific hackathons only (matches Go's IsIndiaSpecific)
    eligibility_keywords: List[str] = field(
        default_factory=list
    )  # Keywords to filter eligibility (e.g., ["engineering", "UG students"])
    eligibility_mode: str = "exclude"  # "include" or "exclude" - if "exclude", removes matches; if "include", keeps only matches


@dataclass
class StorageConfig:
    file_path: str = "data/hackathons.json"
    dedup_days: int = 30
    max_entries: int = 1000
    # Store all scraped hackathons before filtering (optional)
    unfiltered_file_path: str = "data/hackathons_unfiltered.json"
    store_unfiltered: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/scraper.log"
    console: bool = True
    max_size_mb: int = 10
    backup_count: int = 3


@dataclass
class KeywordExpansion:
    """Keyword expansion mapping - field -> list of related keywords"""

    keywords: List[str] = field(default_factory=list)


@dataclass
class KeywordConfig:
    """Configurable keyword expansions - map field names to search keywords"""

    expansions: Dict[str, List[str]] = field(default_factory=dict)

    def get_keywords(self, field: str) -> List[str]:
        """Get expanded keywords for a field"""
        field_lower = field.lower()
        # Direct match
        if field_lower in self.expansions:
            return self.expansions[field_lower]
        # Partial match (e.g., "AI/ML" matches "ai")
        for key in self.expansions:
            if key in field_lower or field_lower in key:
                return self.expansions[key]
        return [field]  # Default: just use the field itself


@dataclass
class Config:
    fields: List[str] = field(default_factory=list)
    email: Optional[EmailConfig] = None
    sources: List[SourceConfig] = field(default_factory=list)
    filters: FiltersConfig = field(default_factory=FiltersConfig())
    storage: StorageConfig = field(default_factory=StorageConfig())
    logging: LoggingConfig = field(default_factory=LoggingConfig())
    keywords_expand: KeywordConfig = field(default_factory=KeywordConfig)


class ConfigManager:
    """Manages configuration loading and validation"""

    DEFAULT_CONFIG_PATH = "config.yaml"

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[Config] = None

    def load(self) -> Config:
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f)

        return self._parse_config(data)

    def _parse_config(self, data: dict) -> Config:
        """Parse raw config dict into Config dataclass"""

        # Parse email config
        email_data = data.get("email", {})
        email_config = None
        if email_data:
            # Resolve environment variable references
            sender_email = resolve_env_var(email_data.get("sender_email", ""))
            sender_password = resolve_env_var(
                email_data.get("sender_password", "SMTP_PASSWD")
            )
            recipient_list_raw = resolve_env_var(email_data.get("recipient_list", ""))

            email_config = EmailConfig(
                smtp_host=email_data.get("smtp_host", "smtp.gmail.com"),
                smtp_port=email_data.get("smtp_port", 587),
                sender_email=sender_email,
                sender_password=sender_password,
                recipient_list=parse_recipient_list(recipient_list_raw),
                use_tls=email_data.get("use_tls", True),
                subject_prefix=email_data.get("subject_prefix", "[Hackathon Scout]"),
            )

        # Parse sources
        sources = []
        for src in data.get("sources", []):
            sources.append(
                SourceConfig(
                    name=src.get("name", ""),
                    enabled=src.get("enabled", True),
                    priority=src.get("priority", 1),
                    base_url=src.get("base_url", ""),
                    search_paths=src.get("search_paths", []),
                    keywords=src.get("keywords", []),
                    selector_card=src.get("selector_card", ""),
                    selector_title=src.get("selector_title", ""),
                    selector_link=src.get("selector_link", ""),
                    selector_date=src.get("selector_date", ""),
                    selector_mode=src.get("selector_mode", ""),
                    selector_desc=src.get("selector_desc", ""),
                    selector_tags=src.get("selector_tags", ""),
                    selector_prize=src.get("selector_prize", ""),
                    use_api=src.get("use_api", False),
                    api_url=src.get("api_url", ""),
                    api_response_format=src.get("api_response_format", ""),
                    per_page=src.get("per_page", 20),
                    max_pages=src.get("max_pages", 0),
                    page_param=src.get("page_param", "page"),
                    per_page_param=src.get("per_page_param", "per_page"),
                    api_headers=src.get("api_headers", {}),
                    api_params=src.get("api_params", {}),
                )
            )

        # Parse filters
        filters_data = data.get("filters", {})
        filters = FiltersConfig(
            min_days_ahead=filters_data.get("min_days_ahead", 3),
            max_days_ahead=filters_data.get("max_days_ahead", 180),
            include_ended=filters_data.get("include_ended", False),
            regions=filters_data.get("regions", []),
            india_only=filters_data.get("india_only", False),
            eligibility_keywords=filters_data.get("eligibility_keywords", []),
            eligibility_mode=filters_data.get("eligibility_mode", "exclude"),
        )

        # Parse storage
        storage_data = data.get("storage", {})
        storage = StorageConfig(
            file_path=storage_data.get("file_path", "data/hackathons.json"),
            dedup_days=storage_data.get("dedup_days", 30),
            max_entries=storage_data.get("max_entries", 500),
            unfiltered_file_path=storage_data.get("unfiltered_file_path", "data/hackathons_unfiltered.json"),
            store_unfiltered=storage_data.get("store_unfiltered", True),
        )

        # Parse logging
        logging_data = data.get("logging", {})
        logging_cfg = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            file=logging_data.get("file", "logs/scraper.log"),
            console=logging_data.get("console", True),
            max_size_mb=logging_data.get("max_size_mb", 10),
            backup_count=logging_data.get("backup_count", 3),
        )

        # Parse keyword expansions
        keywords_expand_data = data.get("keywords_expand", {})
        keywords_expand = KeywordConfig(expansions=keywords_expand_data)

        return Config(
            fields=data.get("fields", []),
            email=email_config,
            sources=sources,
            filters=filters,
            storage=storage,
            logging=logging_cfg,
            keywords_expand=keywords_expand,
        )

    @property
    def config(self) -> Config:
        """Lazy load and cache config"""
        if self._config is None:
            self._config = self.load()
        return self._config


# def get_smtp_password(env_name: str) -> str:
#     """Get SMTP password from environment variable"""
#     password = os.environ.get(env_name)
#     if not password:
#         raise ValueError(f"Environment variable {env_name} not set for SMTP password")
#     return password
