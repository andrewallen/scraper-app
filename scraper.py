# Initial scraper structure - to be developed
import requests
import argparse
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import os
import logging
from urllib.parse import urlparse, urljoin
import feedparser # Import feedparser
from datetime import datetime # Import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to generate a safe filename from a URL
def url_to_filename(url, output_dir):
    parsed_url = urlparse(url)
    # Get path, remove leading/trailing slashes, replace slashes with underscores
    path = parsed_url.path.strip('/').replace('/', '_')
    if not path: # Handle root URL case
        path = urlparse(url).netloc.replace('.', '_') # Use domain name if path is empty
    filename = f"{path}.md"
    return os.path.join(output_dir, filename)

# Function to fetch and scrape content
def scrape_content(url, output_dir, user_agent):
    headers = {
        'User-Agent': user_agent
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return None # Return None to indicate failure

    soup = BeautifulSoup(response.content, 'html.parser')

    # --- Extract Metadata --- 
    title = soup.find('h1')
    title_text = f"# {title.get_text(strip=True)}\n\n" if title else ""

    lead_paragraph = soup.find('p', class_=['gem-c-lead-paragraph', 'govuk-body-l']) # Common classes for lead para
    lead_text = f"{lead_paragraph.get_text(strip=True)}\n\n" if lead_paragraph else ""

    metadata_section = soup.find(class_=['gem-c-metadata', 'govuk-body-s']) # Common classes for metadata
    metadata_text = ""
    formatted_date_prefix = "" # Initialize as empty string
    if metadata_section:
        metadata_items = []
        # Look for 'From:'
        from_term = metadata_section.find('dt', string=lambda t: t and 'From:' in t)
        if from_term:
            from_dd = from_term.find_next_sibling('dd')
            if from_dd:
                metadata_items.append(f"From:\n{from_dd.get_text(separator='\n', strip=True)}\n") # Keep line breaks for multiple departments

        # Look for 'Published'
        published_term = metadata_section.find('dt', string=lambda t: t and 'Published' in t)
        if published_term:
            published_dd = published_term.find_next_sibling('dd')
            if published_dd:
                published_date_str = published_dd.get_text(strip=True)
                metadata_items.append(f"Published:\n{published_date_str}")
                # --- Attempt to parse and format date for filename --- 
                try:
                    # Common format: '28 March 2025'
                    # Handle potential variations if needed (e.g., with time)
                    if ' at ' in published_date_str: # Remove time if present
                         published_date_str = published_date_str.split(' at ')[0]
                    parsed_date = datetime.strptime(published_date_str, '%d %B %Y')
                    formatted_date_prefix = parsed_date.strftime('%Y-%m-%d')
                except ValueError as e:
                    logging.warning(f"Could not parse published date '{published_date_str}' for URL {url}: {e}")
                    formatted_date_prefix = None # Indicate failure to parse
            else:
               formatted_date_prefix = None # No date found
        else:
           formatted_date_prefix = None # No date found
            
        if metadata_items:
            metadata_text = "\n---\n\n" + "\n".join(metadata_items) + "\n\n---\n\n" # Use separators
    # --- Extract Main Content --- 
    # Try primary selector first
    content_area = soup.select_one('main#content .govuk-govspeak')
    if not content_area:
        # Fallback: try finding just main#content if .govuk-govspeak isn't there
        content_area = soup.select_one('main#content')
        if not content_area:
            logging.warning(f"Could not find main content area (.govuk-govspeak or main#content) in {url}")
            # As a last resort, try taking the whole body, but this is likely to be noisy
            content_area = soup.body
            if not content_area:
                 logging.error(f"Could not extract any content from {url}")
                 return None # Cannot proceed

    # Convert the found content area to Markdown
    markdown_content = md(str(content_area), heading_style="ATX")

    # --- Combine and Save --- 
    # Prepend metadata and source URL
    full_markdown_content = f"Source: {url}\n\n{title_text}{lead_text}{metadata_text}{markdown_content}"

    # Create filename from URL path
    parsed_url = urlparse(url)
    domain_name = parsed_url.netloc # Extract domain name
    path_parts = [part for part in parsed_url.path.split('/') if part]
    if not path_parts:
        filename_base = domain_name # Use domain if path is empty
    else:
        filename_base = '_'.join(path_parts)
    filename = f"{filename_base}.md"
    # Sanitize filename (basic example, might need refinement)
    filename = filename.replace(':', '-').replace('/', '_').replace('\\', '_')

    # Prepend date if available
    if formatted_date_prefix:
        filename = f"{formatted_date_prefix}_{filename}"

    # Construct the full output path including the domain subdirectory
    domain_output_dir = os.path.join(output_dir, domain_name)
    os.makedirs(domain_output_dir, exist_ok=True) # Ensure the domain directory exists
    filepath = os.path.join(domain_output_dir, filename)

    # Prepend metadata and source URL to the Markdown content
    full_md_content = f"Source: {url}\n\n{title_text}\n\n{lead_text}\n\n{metadata_text}\n\n---\n\n{markdown_content}"

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_md_content)
        logging.info(f"Saved content from {url} to {filepath}")
        return content_area # Return the soup object of the main content for potential crawling
    except IOError as e:
        logging.error(f"Failed to write file {filepath}: {e}")
        return None # Indicate failure

# --- Helper function to parse a single feed --- 
def parse_feed(feed_url):
    urls_from_feed = []
    logging.info(f"Fetching feed URL: {feed_url}")
    try:
        feed_data = feedparser.parse(feed_url)
        if feed_data.bozo:
             logging.warning(f"Feed may be ill-formed ({feed_url}): {feed_data.bozo_exception}")
        if not feed_data.entries:
             logging.warning(f"No entries found in feed: {feed_url}")
        else:
            for entry in feed_data.entries:
                if 'link' in entry:
                    urls_from_feed.append(entry.link)
                    logging.info(f"  Added URL from feed ({feed_url}): {entry.link}")
                else:
                    logging.warning(f"  Skipping feed entry without link ({feed_url}): {entry.get('title', '[No Title]')}")
    except Exception as e:
        logging.error(f"Failed to parse feed {feed_url}: {e}")
        # Optionally raise or return an empty list on error
    return urls_from_feed

# Function to find relevant sub-links within the content area
def find_sub_links(base_url, content_area):
    sub_links = set()
    if not content_area:
        return list(sub_links)

    base_domain = urlparse(base_url).netloc

    for a_tag in content_area.find_all('a', href=True):
        href = a_tag['href']
        # Construct absolute URL for relative links
        absolute_url = urljoin(base_url, href)
        parsed_absolute_url = urlparse(absolute_url)

        # --- Filter Links ---
        # 1. Must be http or https
        if parsed_absolute_url.scheme not in ['http', 'https']:
            continue
        # 2. Must end with gov.uk domain
        if not parsed_absolute_url.netloc.endswith('gov.uk'):
            continue
        # 3. Optional: Check if it's the *same* subdomain or the main www.gov.uk?
        #    For now, we accept any gov.uk subdomain.
        # 4. Avoid fragments (#) and non-HTML content if possible (basic check)
        if parsed_absolute_url.fragment: # Skip links pointing to page fragments
             continue
        # Crude check for common non-HTML file extensions - might need expansion
        # Add .atom and .rss to exclusions
        if any(absolute_url.lower().endswith(ext) for ext in ['.pdf', '.zip', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.json', '.xml', '.atom', '.rss']):
            continue

        # Add the valid, absolute gov.uk URL
        sub_links.add(absolute_url)

    return list(sub_links)


def main():
    parser = argparse.ArgumentParser(description='Scrape content from gov.uk URLs or an RSS/Atom feed and convert to Markdown.')
    # Make URL input optional if feed URL is provided
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument('urls', metavar='URL', type=str, nargs='*', default=[],
                        help='One or more gov.uk URLs to scrape. Ignored if --feed-url or --feed-file is used.')
    url_group.add_argument('--feed-url', type=str, default=None,
                        help='URL of a single RSS/Atom feed to scrape articles from.')
    url_group.add_argument('--feed-file', type=str, default=None,
                        help='Path to a text file containing a list of RSS/Atom feed URLs (one per line).')

    parser.add_argument('--crawl', action='store_true',
                        help='Enable crawling of sub-links found within the content (applies to non-feed URLs).'
                             ' Note: Crawling is NOT performed on articles found via feed.') # Clarify crawl applies to direct URLs
    parser.add_argument('--same-domain', action='store_true', help='Only crawl links within the same domain as the starting URL.')
    parser.add_argument('--output-dir', type=str, default='output',
                        help='Directory to save the Markdown files (default: output).')
    parser.add_argument('--max-depth', type=int, default=1,
                        help='Maximum crawl depth (1 means only initial URLs, 2 means initial + their links, etc.). Only used if --crawl is specified. Default is 1.')
    parser.add_argument('--user-agent', type=str, default='Mozilla/5.0 (compatible; MyScraperBot/1.0; +http://example.com/bot)',
                        help='Custom User-Agent string for requests.')


    args = parser.parse_args()

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        logging.info(f"Created output directory: {args.output_dir}")

    initial_urls = []
    feed_urls_to_process = []

    if args.feed_url: # Single feed URL
        feed_urls_to_process.append(args.feed_url)
    elif args.feed_file: # File containing multiple feed URLs
        logging.info(f"Reading feed URLs from file: {args.feed_file}")
        try:
            with open(args.feed_file, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'): # Ignore empty lines and comments
                        feed_urls_to_process.append(url)
        except FileNotFoundError:
            logging.error(f"Feed file not found: {args.feed_file}")
            print(f"Error: Feed file not found: {args.feed_file}")
            exit(1)
        except IOError as e:
            logging.error(f"Error reading feed file {args.feed_file}: {e}")
            print(f"Error: Could not read feed file: {args.feed_file}")
            exit(1)
    else:
        initial_urls = args.urls # Use the directly provided URLs if no feed option used

    # Process feeds if any were specified
    if feed_urls_to_process:
        for feed_url in feed_urls_to_process:
            article_urls = parse_feed(feed_url)
            initial_urls.extend(article_urls)

        # Remove duplicates that might come from multiple feeds
        initial_urls = list(dict.fromkeys(initial_urls))

    if not initial_urls:
        logging.warning("No URLs provided directly or via feed(s). Nothing to scrape.")
        exit(0)

    processed_urls = set()
    # Use a dictionary to track URLs and their depth
    # Only apply depth > 1 if crawling is enabled *and* we are not processing feed URLs
    start_depth = 1
    # Determine max depth: Apply only if crawl is enabled AND no feed option was used
    is_feed_mode = bool(args.feed_url or args.feed_file)
    max_process_depth = args.max_depth if args.crawl and not is_feed_mode else 1

    urls_to_process = {url: start_depth for url in initial_urls} # Start at depth 1

    while urls_to_process:
        # Get the next URL to process (simple approach, not prioritizing depth levels)
        # A more sophisticated approach might use separate queues per depth level
        current_url, current_depth = urls_to_process.popitem()

        if current_url in processed_urls:
            continue

        # Check domain before processing
        parsed_url = urlparse(current_url)
        if not parsed_url.netloc or not parsed_url.netloc.endswith('gov.uk'):
            logging.warning(f"Skipping non-gov.uk or invalid URL: {current_url}")
            processed_urls.add(current_url) # Mark as processed to avoid loops
            continue

        logging.info(f"Processing URL (Depth {current_depth}): {current_url}")
        # Pass user_agent to scrape_content
        content_area = scrape_content(current_url, args.output_dir, args.user_agent)
        processed_urls.add(current_url)

        # Determine if crawling should be enabled
        should_crawl = args.crawl  # Correctly base crawling on the --crawl flag

        # Create output directory if it doesn't exist
        output_dir = args.output_dir

        # Find and add sub-links if crawling is enabled and depth allows
        if should_crawl and content_area and current_depth < args.max_depth:
            sub_links = find_sub_links(current_url, content_area)
            next_depth = current_depth + 1
            current_domain = urlparse(current_url).netloc # Get domain of the current page
            for link in sub_links:
                if link not in processed_urls and link not in urls_to_process:
                     # Check if crawling is restricted to the same domain
                     if args.same_domain:
                         link_domain = urlparse(link).netloc
                         if link_domain != current_domain:
                             logging.debug(f"Skipping different domain link ({link_domain} != {current_domain}): {link}")
                             continue # Skip this link

                     # If checks pass, add to queue
                     urls_to_process[link] = next_depth
                     logging.info(f"  Queueing sub-link (Depth {next_depth}): {link}")


    logging.info(f"Scraping process finished. Processed {len(processed_urls)} unique URLs.")

if __name__ == "__main__":
    main()
