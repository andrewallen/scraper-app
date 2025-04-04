# Gov.uk Content Scraper

This application scrapes content from specified gov.uk URLs, converts the main content to Markdown, and saves it locally. It can optionally crawl and scrape sub-pages linked from the initial URLs.

## Features

*   Scrape content from one or more gov.uk URLs.
*   Convert the main article content to Markdown format.
*   Save the scraped content as individual Markdown files.
*   Optionally crawl sub-pages found within the main content area.

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
# Scrape specific URLs
python scraper.py <url1> [url2 ...] [--crawl] [--max-depth N] [--output-dir OUTPUT_DIRECTORY]

# Scrape URLs from a feed
python scraper.py --feed-url <feed_url> [--output-dir OUTPUT_DIRECTORY]
```

**Arguments:**

*   `url`: One or more gov.uk URLs to scrape. (Mutually exclusive with `--feed-url`).
*   `--feed-url`: URL of an RSS/Atom feed. If provided, the script scrapes the article URLs found in the feed. (Mutually exclusive with providing specific URLs).
*   `--crawl`: (Optional) If specified, the scraper will also process relevant sub-links found on the initial pages *when specific URLs are provided*. Crawling is disabled when using `--feed-url`.
*   `--max-depth`: (Optional) Specify the maximum crawl depth (default: 1). Only used if `--crawl` is specified *and specific URLs are provided*.
*   `--output-dir`: (Optional) Specify the directory where Markdown files should be saved. Defaults to 'output'.
*   `--user-agent`: (Optional) Specify a custom User-Agent string for HTTP requests.

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
