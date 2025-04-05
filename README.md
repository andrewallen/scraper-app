# Web Content Scraper

This application scrapes content from specified URLs or RSS/Atom feeds, converts the main content to Markdown, saves linked documents, and saves the result locally. It can optionally crawl and scrape sub-pages linked from the initial URLs.

## Features

*   Scrape content from one or more URLs or feed sources.
*   Convert the main article content to Markdown format.
*   Identify and download linked documents (PDFs, DOCX, etc.) from scraped pages.
*   Save scraped text content as individual Markdown files, organized by domain.
*   Save downloaded documents in the same domain-specific directories.
*   Optionally crawl sub-pages found within the main content area.
*   Attempts to extract structured metadata (Title, Lead Paragraph, Author, Published Date) if available in common formats.
*   Falls back to using the entire page body if specific content selectors fail.
*   Supports concurrent scraping and downloading using threads for faster processing.

## Code Structure

The application is structured into a modular package `scraper_app` to enhance organization, maintainability, and readability:

*   **`scraper.py`**: The main command-line interface and entry point. Handles argument parsing, orchestrates the scraping workflow (fetching initial URLs, managing the thread pool, processing results), and sets up logging.
*   **`scraper_app/`**: The core Python package.
    *   **`__init__.py`**: Marks the directory as a Python package.
    *   **`constants.py`**: Centralizes constant values like default configurations (output directory, user agent, timeouts, worker counts), CSS selectors (primarily targeting gov.uk structure, but with fallbacks considered), and filename length limits.
    *   **`utils.py`**: Provides general utility functions, currently including `sanitize_filename` for creating filesystem-safe filenames from potentially problematic strings.
    *   **`storage.py`**: Manages file system interactions. Includes logic for generating structured filenames and directory paths based on URLs and dates (`generate_filename`) and handling the download and saving of binary files/documents (`download_binary_file`), determining file types where possible.
    *   **`parse_html.py`**: Contains the logic for handling individual HTML pages. It fetches the page (`requests`), parses it (`BeautifulSoup`), attempts to extract metadata and the main content based on `constants.py` selectors (falling back to `<body>`), converts content to Markdown (`markdownify`), finds linked documents and potential sub-links for crawling, and coordinates saving the Markdown content via `storage.py`.
    *   **`parse_feed.py`**: Handles fetching and parsing of RSS/Atom feeds using `feedparser` to extract a list of article URLs for processing.

This modular design allows for easier testing and modification of individual components (e.g., adding new content selectors, changing storage methods).

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

*   `URL`: (Positional) One or more URLs to scrape. Required if no feed options are provided.
*   `--feed-url <FEED_URL>`: URL of a single RSS/Atom feed. Articles from the feed will be scraped.
*   `--feed-file <FEED_FILE>`: Path to a text file containing multiple feed URLs (one per line). Articles from all feeds will be scraped.
*   `-o DIR`, `--output-dir DIR`: Directory to save the resulting Markdown and document files (default: `output`). Files will be organized into subdirectories based on the domain name.
*   `--user-agent UA`: Custom User-Agent string for HTTP requests.
*   `--crawl`: Enable crawling of relevant sub-links found on scraped pages.
*   `--max-depth N`: Maximum crawl depth when `--crawl` is enabled. `0` means only scrape the initial URLs (from args or feeds), `1` means initial URLs plus the links found within them, etc.
*   `--same-domain`: When crawling, only follow links that are on the exact same domain (e.g., `www.example.com`) as the page they were found on.
*   `-w N`, `--workers N`: Number of parallel workers (threads) to use for scraping and downloading (default: calculated based on CPU count).

**Examples:**

*   Scrape a single page:
    ```bash
    python scraper.py https://example.com/some-page
    ```
*   Scrape multiple pages and save to a specific directory:
    ```bash
    python scraper.py https://example.com/page-one https://anothersite.org/article --output-dir ./scraped_content
    ```
*   Scrape a page and crawl its sub-links (depth 2), staying on the same domain:
    ```bash
    python scraper.py https://example.com/main-topic --crawl --max-depth 2 --same-domain
    ```
*   Scrape all articles from an Atom feed:
    ```bash
    python scraper.py --feed-url 'https://example.com/feed.atom' --output-dir ./feed_articles
    ```

## How it Works

1.  The script parses command-line arguments.
2.  It determines the initial list of URLs to process, either from direct arguments, a single feed URL, or a file containing multiple feed URLs.
3.  A thread pool (`ThreadPoolExecutor`) is created to manage concurrent tasks.
4.  Initial URLs are submitted to the pool for processing by the `scrape_and_process` function.
5.  `scrape_and_process` calls `parse_and_save_html` (from `parse_html.py`):
    *   Fetches the HTML using `requests`.
    *   Parses the HTML using `BeautifulSoup`.
    *   Attempts to find the main content area using predefined CSS selectors (defined in `constants.py`). If specific selectors fail, it falls back to using the entire `<body>`.
    *   Attempts to extract metadata (title, lead paragraph, published date, etc.) based on common patterns.
    *   Identifies links to potential documents (PDF, DOCX, etc.) within attachment sections or based on URL patterns.
    *   Converts the extracted main content HTML to Markdown using `markdownify`.
    *   Generates a filename and path (using `storage.py`).
    *   Saves the final Markdown content (Source URL + metadata + content + document links) to the file.
    *   Returns the parsed BeautifulSoup object for the content area (for crawling) and the list of found document URLs.
6.  Back in `scrape_and_process`:
    *   Any discovered document URLs are submitted to the thread pool for download using `download_binary_file` (from `storage.py`).
    *   If crawling is enabled (`--crawl`) and the current depth is less than `--max-depth`:
        *   `find_sub_links` (from `parse_html.py`) is called to find potential sub-links within the processed page's content.
        *   Valid sub-links (that haven't been processed and match `--same-domain` if enabled) are submitted back to the thread pool for processing, incrementing the depth.
7.  A central lock (`threading.Lock`) ensures that the set of processed URLs (`processed_urls`) is updated safely by multiple threads to prevent redundant work.
8.  The main thread waits for all submitted tasks (and any tasks they spawn) to complete, logging progress and results.

## Disclaimer

Web scraping should be done responsibly and ethically. Always check a website's `robots.txt` file and terms of service before scraping. Respect server load; avoid overly aggressive scraping. This tool is intended for processing publicly available information.
