"""Scrapers package"""

from .base import BaseScraper, ScraperFactory, register_scrapers

# Auto-register scrapers on import
register_scrapers()
