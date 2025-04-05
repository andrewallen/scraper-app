"""Handles fetching, parsing, and saving content from individual HTML pages."""

import logging
import requests
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md
from urllib.parse import urlparse, urljoin
from datetime import datetime
from typing import List, Tuple, Optional

from .constants import (
    LEAD_PARAGRAPH_SELECTORS,
    METADATA_SELECTORS,
    CONTENT_AREA_SELECTORS,
    ATTACHMENT_SELECTORS,
    ATTACHMENT_LINK_SELECTOR,
    REQUEST_TIMEOUT
)
from .storage import generate_filename

def find_sub_links(content_soup: BeautifulSoup, base_url: str) -> List[str]:
    """Finds potential sub-links (likely other pages to scrape) within the content area.

    Args:
        content_soup: The BeautifulSoup object of the content area to search within.
        base_url: The base URL to resolve relative links.

    Returns:
        A list of absolute URLs found within the content area.
    """
    sub_links = []
    if not content_soup:
        return sub_links

    # Find all links within the main content area
    for a_tag in content_soup.find_all('a', href=True):
        href = a_tag['href']
        try:
            absolute_url = urljoin(base_url, href)
            parsed_absolute_url = urlparse(absolute_url)

            # Basic filtering:
            # - Must be HTTP/HTTPS
            # - Must have a domain (netloc)
            # - Avoid fragments (# in path or original href)
            # - Avoid mailto/tel etc.
            if (parsed_absolute_url.scheme in ['http', 'https'] and
                parsed_absolute_url.netloc and
                '#' not in href and '#' not in parsed_absolute_url.path):

                # Add more robust check for file extensions if needed
                # e.g., if not any(absolute_url.lower().endswith(ext) for ext in ['.pdf', '.zip']):
                sub_links.append(absolute_url)

        except Exception as e:
            logging.warning(f"Could not process link '{href}' found on {base_url}: {e}")

    return sub_links

def parse_and_save_html(url: str, output_dir: str, user_agent: str) -> Tuple[Optional[BeautifulSoup], List[str]]:
    """Fetches HTML, parses main content, extracts metadata/docs, saves as Markdown.

    Args:
        url: The URL to scrape.
        output_dir: The base directory to save the Markdown file.
        user_agent: The User-Agent string for the request.

    Returns:
        A tuple containing (BeautifulSoup object of the *main content area* or None on failure,
                         List of discovered document URLs).
    """
    headers = {'User-Agent': user_agent}
    content_area_soup: Optional[BeautifulSoup] = None # Parsed object of the specific content area
    document_urls: List[str] = []
    formatted_date_prefix: Optional[str] = None

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.Timeout:
         logging.error(f"Timeout fetching {url}")
         return None, document_urls
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error fetching {url}: {e.status_code} {e.response.reason}")
        return None, document_urls
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return None, document_urls

    soup = BeautifulSoup(response.content, 'html.parser')

    # --- Metadata Extraction (Heuristics based on common patterns, e.g., gov.uk) ---
    metadata_dict = {}
    title = soup.title.string if soup.title else "No Title Found"
    title_text = f"# {title}\n\n"

    lead_paragraph_text = ""
    for selector in LEAD_PARAGRAPH_SELECTORS:
        lead_paragraph = soup.select_one(selector)
        if lead_paragraph:
            lead_paragraph_text = f"{lead_paragraph.get_text(strip=True)}\n\n"
            break

    metadata_section = None
    for selector in METADATA_SELECTORS:
        metadata_section = soup.select_one(selector)
        if metadata_section:
            break

    metadata_text = ""
    if metadata_section:
        metadata_items = []
        from_term = metadata_section.find('dt', string=lambda t: t and 'From:' in t)
        if from_term:
            from_dd = from_term.find_next_sibling('dd')
            if from_dd:
                metadata_items.append(f"From:\n{from_dd.get_text(separator='\\n', strip=True)}\n")

        published_term = metadata_section.find('dt', string=lambda t: t and 'Published' in t)
        if published_term:
            published_dd = published_term.find_next_sibling('dd')
            if published_dd:
                published_date_str = published_dd.get_text(strip=True)
                metadata_items.append(f"Published:\n{published_date_str}")
                try:
                    date_part = published_date_str.split(' at ')[0]
                    parsed_date = datetime.strptime(date_part, '%d %B %Y')
                    formatted_date_prefix = parsed_date.strftime('%Y-%m-%d')
                except ValueError as e:
                    logging.warning(f"Could not parse published date '{published_date_str}' for URL {url}: {e}")

        if metadata_items:
            metadata_text = "\n---\n\n" + "\n".join(metadata_items) + "\n\n---\n\n"

    # --- Extract Main Content --- (Copied and adapted from original scrape_content)
    content_area: Optional[Tag] = None
    for selector in CONTENT_AREA_SELECTORS:
         content_area = soup.select_one(selector)
         if content_area:
              break

    if not content_area:
        logging.warning(f"Could not find main content area using selectors {CONTENT_AREA_SELECTORS} in {url}. Falling back to body.")
        content_area = soup.body
        if not content_area:
            logging.error(f"Could not extract any content (not even body) from {url}")
            return None, document_urls

    # Store the soup object for the specific content area found (for crawling)
    content_area_soup = content_area

    # Convert the found content area to Markdown
    markdown_content = md(str(content_area), heading_style="ATX") if content_area else ""

    # --- Link Finding (Heuristics based on structure and file extensions) ---
    document_links_md = ""
    attachment_sections: List[Tag] = []
    for selector in ATTACHMENT_SELECTORS:
        attachment_sections.extend(soup.select(selector))

    if attachment_sections:
        doc_links = []
        for section in attachment_sections:
            link_tag = section.select_one(ATTACHMENT_LINK_SELECTOR)
            if link_tag and link_tag.has_attr('href'):
                href = link_tag['href']
                text = link_tag.get_text(strip=True) or href
                try:
                    absolute_url = urljoin(url, href)
                    if absolute_url.startswith('http') and '#' not in absolute_url.split('/')[-1]:
                        # Basic check to avoid linking to web pages as documents
                        if not absolute_url.lower().endswith( ('.html', '.htm', '.php', '.asp', '.aspx') ):
                             doc_links.append(f"- [{text}]({absolute_url})")
                             document_urls.append(absolute_url)
                        else:
                             logging.debug(f"Skipping likely web page link in documents section: {absolute_url}")
                except Exception as e:
                     logging.warning(f"Error processing potential document link '{href}' on page {url}: {e}")

        if doc_links:
            document_links_md = "\n\n## Documents\n\n" + "\n".join(doc_links)

    # --- Combine and Save --- (Copied and adapted from original scrape_content)
    full_md_content = f"Source: {url}\n\n{title_text}{lead_paragraph_text}{metadata_text}---\n\n{markdown_content}{document_links_md}"

    try:
        _, filepath = generate_filename(url, output_dir, formatted_date_prefix, ".md")
    except Exception as e:
         logging.error(f"Error generating filename for {url}: {e}")
         return content_area_soup, document_urls

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_md_content)
        logging.info(f"Saved content from {url} to {filepath}")
        return content_area_soup, document_urls
    except IOError as e:
        logging.error(f"Failed to write file {filepath}: {e}")
        return content_area_soup, document_urls # Return soup/docs even if save fails
