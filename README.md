# Hackathon Scout

A Python-based hackathon discovery tool that scrapes upcoming hackathons from multiple sources, filters by configurable criteria, and sends daily email notifications.

## Features

- **Multi-source scraping**: Fetches hackathons from 7 platforms (Devpost, Unstop, Devfolio, Hack2Skill, WhereUElevate, HackerEarth, Devnovate)
- **Config-driven**: Fully configurable via YAML - add sources and filters without code changes
- **Smart filtering**: Filter by date range, regions, eligibility criteria, and India-specific events
- **Deduplication**: Prevents sending same hackathon twice within configured period
- **Unfiltered storage**: Stores all scraped data separately before filtering
- **Email notifications**: HTML-formatted emails with platform name, dates, and mode
- **GitHub Actions**: Ready-to-use daily scheduled workflow (runs at midnight UTC)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

The `config.yaml` is already configured with all sources. Set environment variables for email:

```bash
# Linux/macOS
export SENDER_EMAIL="you@example.com"
export SMTP_PASSWD="your-app-password"
export RECIPIENT_LIST="team@example.com,other@example.com"

# Windows (PowerShell)
$env:SENDER_EMAIL="you@example.com"
$env:SMTP_PASSWD="your-app-password"
$env:RECIPIENT_LIST="team@example.com"
```

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833).

### 3. Test Run

```bash
# Check config validity
python -m src.cli --check

# List available sources
python -m src.cli --sources

# Run scraper manually
python -m src.cli
```

### 4. GitHub Actions (Recommended)

Add these secrets in GitHub repo Settings → Secrets:
- `SMTP_PASSWD`: Your email app password
- `SENDER_EMAIL`: Sender email address
- `RECIPIENT_LIST`: Comma-separated recipient emails

The workflow runs daily at 00:00 UTC automatically.

## Configuration Reference

### Email Settings

```yaml
email:
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  sender_email: ${SENDER_EMAIL}      # From environment
  sender_password: ${SMTP_PASSWD}    # From environment
  recipient_list: ${RECIPIENT_LIST}  # From environment
  use_tls: true
```

### Sources (7 Platforms)

All sources are enabled by default:

| Source | Priority | Description |
|--------|----------|-------------|
| devpost | 1 | Major hackathon platform |
| unstop | 2 | Competitions & hackathons |
| devfolio | 3 | Indian hackathon platform |
| hack2skill | 4 | Hackathons & competitions |
| whereuelevate | 5 | Internships & hackathons |
| hackerearth | 6 | Coding challenges |
| devnovate | 7 | Hackathon platform |

### Filters

```yaml
filters:
  min_days_ahead: 0        # Minimum days until start
  max_days_ahead: 180      # Maximum days until start
  include_ended: false     # Include ended hackathons
  regions:                 # Filter by city/region (for in-person)
    - "Bengaluru"
  india_only: false        # Filter to India-specific only
  eligibility_keywords:    # Filter by participation criteria
    - "students"
    - "UG"
  eligibility_mode: "exclude"  # "exclude" or "include"
```

### Storage

```yaml
storage:
  file_path: "data/hackathons.json"
  dedup_days: 30
  max_entries: 1000
  unfiltered_file_path: "data/hackathons_unfiltered.json"
  store_unfiltered: true
```

## Project Structure

```
hackathon_scout/
├── config.yaml          # Configuration (uses ${ENV_VAR})
├── requirements.txt     # Python dependencies
├── .gitignore
├── .github/
│   └── workflows/
│       └── daily-scrape.yml
├── src/
│   ├── __init__.py
│   ├── cli.py           # CLI entry point
│   ├── config.py        # Config manager with env var resolution
│   ├── models.py        # Hackathon data models
│   ├── storage.py       # JSON storage with deduplication
│   ├── emailer.py       # Email sender
│   ├── orchestrator.py  # Main coordinator
│   └── scrapers/        # Platform scrapers
│       ├── __init__.py
│       ├── base.py
│       ├── devpost_scraper.py
│       ├── unstop_scraper.py
│       ├── devfolio_scraper.py
│       ├── hack2skill_scraper.py
│       ├── whereuelevate_scraper.py
│       ├── hackerearth_scraper.py
│       ├── devnovate_scraper.py
│       ├── mlh_scraper.py
│       ├── reskill_scraper.py
│       └── generic_scraper.py
├── data/                # Storage (created on first run)
│   ├── hackathons.json
│   └── hackathons_unfiltered.json
└── logs/                # Logs (created on first run)
    └── scraper.log
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SMTP_PASSWD` | Email app password | Yes |
| `SENDER_EMAIL` | Sender email address | Yes |
| `RECIPIENT_LIST` | Comma-separated recipient emails | Yes |

## Security

- Environment variables are resolved at config load time
- Credentials are **never** logged or printed
- Only generic messages like "Email notifier configured for N recipients" are logged

## License

MIT
