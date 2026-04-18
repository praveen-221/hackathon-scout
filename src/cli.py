"""
CLI entry point for Hackathon Scout
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .orchestrator import HackathonScraper


# Load .env file at startup
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


def main():
    parser = argparse.ArgumentParser(
        description="Hackathon Scout - Scrape and notify about upcoming hackathons",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli                    # Run with default config.yaml
  python -m src.cli -c custom.yaml      # Use custom config file
  python -m src.cli --check             # Validate config only
  python -m src.cli --sources           # List available scraper sources
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        default=os.environ.get("CONFIG_PATH", "config.yaml"),
        help="Path to configuration file (default: config.yaml)",
    )

    parser.add_argument(
        "--check", action="store_true", help="Validate configuration and exit"
    )

    parser.add_argument(
        "--sources", action="store_true", help="List available scraper sources and exit"
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Change to script directory for relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    os.chdir(project_dir)

    # Check config
    if args.check:
        from .config import ConfigManager

        try:
            config = ConfigManager(args.config).load()
            print(f"[OK] Configuration valid")
            print(f"  Fields: {', '.join(config.fields)}")
            print(f"  Sources: {len([s for s in config.sources if s.enabled])} enabled")
            print(f"  Email: {'configured' if config.email else 'not configured'}")
            return 0
        except Exception as e:
            print(f"[ERROR] Configuration error: {e}")
            return 1

    # List sources
    if args.sources:
        from .scrapers import ScraperFactory, register_scrapers

        register_scrapers()

        print("Available scraper sources:")
        for name in ScraperFactory.get_available():
            print(f"  - {name}")
        return 0

    # Run scraper
    scraper = HackathonScraper(args.config)

    try:
        total, new = asyncio.run(scraper.run())

        print(f"\nDone. Total: {total}, New: {new}")
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
