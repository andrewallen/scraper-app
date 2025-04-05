# Gov.uk Content Scraper

This application scrapes content from specified gov.uk URLs, converts the main content to Markdown, and saves it locally. It can optionally crawl and scrape sub-pages linked from the initial URLs.

## Features

*   Scrape content from one or more gov.uk URLs.
*   Convert the main article content to Markdown format.
*   Save the scraped content as individual Markdown files.
*   Optionally crawl sub-pages found within the main content area.

## Code Structure

The application has been refactored into a modular structure to improve organization, maintainability, and readability. The core logic is now separated into specific components within the `scraper_app` directory:

*   **`scraper.py`**: The main entry point script. It handles command-line argument parsing, orchestrates the scraping process, and manages concurrency using threads.
*   **`scraper_app/`**: A Python package containing the core modules.
    *   **`__init__.py`**: Makes `scraper_app` a package.
    *   **`constants.py`**: Defines constants used throughout the application, such as default configuration values (output directory, user agent, timeouts), and CSS selectors for identifying content areas.
    *   **`utils.py`**: Contains general utility functions, like `sanitize_filename` for creating safe filenames.
    *   **`storage.py`**: Handles file system operations, including generating appropriate filenames based on URLs and dates (`generate_filename`) and downloading binary files (`download_binary_file`).
    *   **`parse_html.py`**: Responsible for fetching HTML content, parsing it using BeautifulSoup, extracting the main content and metadata, identifying document links, finding sub-links for crawling, and converting HTML to Markdown (`parse_and_save_html`, `find_sub_links`).
    *   **`parse_feed.py`**: Handles the parsing of RSS/Atom feeds to extract article URLs (`parse_feed`).

This separation of concerns makes the codebase easier to understand, test, and modify.

## Requirements

*   Python 3.x
*   Libraries listed in `requirements.txt`

## Installation

1.  Clone this repository or download the source code.
2.  Navigate to the project directory in your terminal.
3.  Install the required libraries:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

```bash
# Scrape specific URLs (optionally crawl links)
python scraper.py <url1> [url2 ...] [-o DIR] [--user-agent UA] [--crawl] [--max-depth N] [--same-domain] [-w N]

# Scrape URLs from a single feed (crawling can be enabled)
python scraper.py --feed-url <feed_url> [-o DIR] [--user-agent UA] [--crawl] [--max-depth N] [--same-domain] [-w N]

# Scrape URLs from multiple feeds listed in a file (crawling can be enabled)
python scraper.py --feed-file <path_to_feeds.txt> [-o DIR] [--user-agent UA] [--crawl] [--max-depth N] [--same-domain] [-w N]
```

**Arguments:**

*   `URL`: (Positional) One or more gov.uk URLs to scrape. Used if no feed options are provided.
*   `--feed-url <FEED_URL>`: URL of a single RSS/Atom feed to process. Articles from the feed will be scraped.
*   `--feed-file <FEED_FILE>`: Path to a text file containing multiple feed URLs (one per line). Articles from all feeds will be scraped.
*   `-o DIR`, `--output-dir DIR`: Directory to save the resulting Markdown files (default: `output`).
*   `--user-agent UA`: Custom User-Agent string for HTTP requests.
*   `--crawl`: Enable crawling of relevant sub-links (within `gov.uk`) found on scraped pages.
*   `--max-depth N`: Maximum crawl depth when `--crawl` is enabled. `0` means only scrape the initial URLs (from args or feeds), `1` means initial URLs plus the links found within them, etc. Requires `--crawl`.
*   `--same-domain`: When crawling, only follow links that are on the exact same domain (e.g., `www.gov.uk`) as the page they were found on. Requires `--crawl`.
*   `-w N`, `--workers N`: Number of parallel workers (threads) to use for scraping (default: CPU count or 4).

**Examples:**

*   Scrape a single page:
    ```bash
    python scraper.py https://www.gov.uk/some-page
    ```
*   Scrape multiple pages and save to a specific directory:
    ```bash
    python scraper.py https://www.gov.uk/page-one https://www.gov.uk/page-two --output-dir ./scraped_content
    ```
*   Scrape a page and crawl its sub-links (depth 2):
    ```bash
    python scraper.py https://www.gov.uk/main-topic --crawl --max-depth 2
    ```
*   Scrape all articles from an Atom feed:
    ```bash
    python scraper.py --feed-url 'https://www.gov.uk/government/organisations/government-digital-service.atom' --output-dir ./gds_feed_articles
    ```

## How it Works

1.  The script fetches the HTML content of the provided URL(s).
2.  It uses BeautifulSoup to parse the HTML and identify the main content section (heuristics based on common gov.uk page structures might be used).
3.  The HTML of the main content is converted to Markdown using the `markdownify` library.
4.  The Markdown content is saved to a `.md` file named after the URL slug in the specified output directory.
5.  If `--feed-url` is provided, the script first fetches and parses the feed to get a list of article URLs to process.
6.  If specific URLs are provided *and* `--crawl` is enabled, it looks for links within the main content area that point to other gov.uk pages and repeats the process for those URLs (up to `--max-depth`, avoiding loops and external links).

## Disclaimer

Web scraping should be done responsibly and ethically. Ensure you comply with the `robots.txt` file and terms of service of gov.uk. This tool is intended for processing publicly available information for analysis and use with LLMs. Excessive scraping can put a strain on website servers.
