\
from typing import List

# --- Constants for Selectors ---
LEAD_PARAGRAPH_SELECTORS: List[str] = ['p.gem-c-lead-paragraph', 'p.govuk-body-l']
METADATA_SELECTORS: List[str] = ['.gem-c-metadata', '.govuk-body-s']
CONTENT_AREA_SELECTORS: List[str] = ['main#content .govuk-govspeak', 'main#content']
ATTACHMENT_SELECTORS: List[str] = ['section.gem-c-attachment', 'div.gem-c-attachment']
ATTACHMENT_LINK_SELECTOR: str = '.gem-c-attachment__link'

# --- Other Constants ---
DEFAULT_USER_AGENT: str = 'Mozilla/5.0 (compatible; MyScraperBot/1.0; +http://example.com/bot)'
DEFAULT_OUTPUT_DIR: str = 'output'
REQUEST_TIMEOUT: int = 20 # seconds for HTML pages
DOWNLOAD_TIMEOUT: int = 60 # seconds for binary files
DEFAULT_MAX_DEPTH: int = 1
DEFAULT_WORKERS: int = 4 # Fallback if cpu_count fails
MAX_FILENAME_LEN: int = 200
