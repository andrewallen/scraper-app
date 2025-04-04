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
import concurrent.futures # Added for parallel processing
import threading # Added for locks
import re # Added for regular expressions

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
        return None, [] # Return None to indicate failure

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
                 return None, [] # Cannot proceed

    # Convert the found content area to Markdown
    markdown_content = md(str(content_area), heading_style="ATX")

    # --- Extract Document Links --- 
    document_links_md = ""
    document_urls = [] # Initialize list to store extracted document URLs
    attachment_sections = soup.select('section.gem-c-attachment, div.gem-c-attachment') # Select common attachment containers
    if attachment_sections:
        doc_links = []
        for section in attachment_sections:
            link_tag = section.select_one('.gem-c-attachment__link') # Common link class within attachments
            if link_tag and link_tag.has_attr('href'):
                href = link_tag['href']
                text = link_tag.get_text(strip=True)
                absolute_url = urljoin(url, href)
                # Exclude non-http links and potentially links to the page itself if needed
                if absolute_url.startswith('http'):
                    doc_links.append(f"- [{text}]({absolute_url})")
                    document_urls.append(absolute_url) # Store the URL

        if doc_links:
            document_links_md = "\n\n## Documents\n\n" + "\n".join(doc_links)

    # --- Combine and Save --- 
    # Prepend metadata and source URL
    full_md_content = f"Source: {url}\n\n{title_text}\n\n{lead_text}\n\n{metadata_text}\n\n---\n\n{markdown_content}{document_links_md}"

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

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_md_content)
        logging.info(f"Saved content from {url} to {filepath}")
        return content_area, document_urls # Return soup object and list of discovered doc URLs
    except IOError as e:
        logging.error(f"Failed to write file {filepath}: {e}")
        return None, [] # Indicate failure, return empty list for doc_urls

# Function to download binary files (like PDFs) directly
def download_binary_file(url, output_dir, user_agent):
    """Downloads a binary file from a URL and saves it.

    Args:
        url (str): The URL of the binary file.
        output_dir (str): The base directory to save the file.
        user_agent (str): The User-Agent string for the request.

    Returns:
        str: The URL if download and save were successful, None otherwise.
    """
    headers = {
        'User-Agent': user_agent
    }
    filepath = None # Initialize filepath to handle potential errors before assignment
    try:
        logging.debug(f"Attempting to download binary file: {url}")
        response = requests.get(url, headers=headers, stream=True, timeout=60) # Timeout for request
        response.raise_for_status() # Check for HTTP errors

        # Determine filename from URL path
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = f"downloaded_{parsed_url.netloc}.bin"
            logging.warning(f"Could not determine filename from URL path: {url}. Using {filename}")
        
        # Sanitize filename
        filename = filename.replace(':', '-').replace('/', '_').replace('\\', '_')

        # Optional: Add date prefix if date pattern found in URL path (for consistency)
        formatted_date_prefix = ""
        date_match = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', parsed_url.path)
        if date_match:
            year, month, day = map(int, date_match.groups())
            try:
                file_date = datetime(year, month, day)
                formatted_date_prefix = file_date.strftime('%Y-%m-%d')
                filename = f"{formatted_date_prefix}_{filename}"
            except ValueError:
                logging.warning(f"Invalid date {year}-{month}-{day} in binary URL path {parsed_url.path}, skipping prefix.")
        
        # Create domain-specific directory
        domain_name = parsed_url.netloc
        domain_output_dir = os.path.join(output_dir, domain_name)
        os.makedirs(domain_output_dir, exist_ok=True)
        filepath = os.path.join(domain_output_dir, filename)

        # Save the file chunk by chunk
        bytes_written = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    bytes_written += len(chunk)
        
        if bytes_written == 0:
            logging.warning(f"Downloaded file {filepath} appears empty (0 bytes).")
        
        logging.info(f"Saved binary file from {url} to {filepath} ({bytes_written} bytes)")
        return url # Success
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download binary file {url}: {e}")
        return None
    except IOError as e:
        logging.error(f"Failed to write binary file {filepath}: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error downloading {url}: {e}")
        # Clean up partial file if download failed mid-way
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
                logging.info(f"Cleaned up partially written file: {filepath}")
            except OSError as rm_err:
                logging.error(f"Failed to clean up partial file {filepath}: {rm_err}")
        return None

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
    url_group = parser.add_mutually_exclusive_group(required=False) # Changed required to False temporarily
    url_group.add_argument('urls', metavar='URL', type=str, nargs='*', default=[],
                        help='One or more gov.uk URLs to scrape. Used if no feed options are provided.')
    url_group.add_argument('--feed-url', type=str, default=None,
                        help='URL of a single RSS/Atom feed to process.')
    url_group.add_argument('--feed-file', type=str, default=None,
                        help='Path to a file containing multiple feed URLs (one per line).')

    parser.add_argument('-o', '--output-dir', type=str, default='output',
                        help='Directory to save Markdown files.')
    parser.add_argument('--user-agent', type=str, default='ScraperBot/1.0 (+http://example.com/bot)',
                        help='User-Agent string for requests.')
    parser.add_argument('--max-depth', type=int, default=0, # Default to 0 (no crawling beyond initial URLs)
                        help='Maximum crawl depth (0=initial URLs only, 1=initial+links, etc.). Requires --crawl.')
    parser.add_argument('--crawl', action='store_true',
                        help='Enable crawling of sub-links found within scraped pages.')
    parser.add_argument('--same-domain', action='store_true',
                        help='When crawling, only follow links within the same domain as the parent page.')
    parser.add_argument('-w', '--workers', type=int, default=os.cpu_count() or 4, # Default to CPU count or 4
                        help='Number of parallel workers for scraping.')

    args = parser.parse_args()

    # --- Input Validation --- 
    if not args.urls and not args.feed_url and not args.feed_file:
        parser.error('At least one of URL, --feed-url, or --feed-file must be provided.')

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    initial_urls_from_args = set(args.urls) # Use a set to avoid duplicates initially
    feed_urls_to_parse = []

    # --- Gather Feed URLs --- 
    if args.feed_url:
        feed_urls_to_parse.append(args.feed_url)
    elif args.feed_file:
        try:
            with open(args.feed_file, 'r') as f:
                # Read lines, strip whitespace, ignore empty lines and comments
                feed_urls_to_parse = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            logging.info(f"Read {len(feed_urls_to_parse)} feed URLs (ignoring comments/blanks) from {args.feed_file}")
            if not feed_urls_to_parse:
                logging.warning(f"No valid feed URLs found in {args.feed_file} after filtering.")
        except FileNotFoundError:
            logging.error(f"Feed file not found: {args.feed_file}")
            return # Exit if feed file is specified but not found
        except Exception as e:
            logging.error(f"Error reading feed file {args.feed_file}: {e}")
            return

    # --- Parse Feeds (in parallel if multiple) --- 
    if feed_urls_to_parse:
        logging.info(f"Parsing {len(feed_urls_to_parse)} feeds using up to {args.workers} workers...")
        urls_from_all_feeds = set()
        # Use a smaller number of workers for feed parsing if there are few feeds
        feed_workers = min(args.workers, len(feed_urls_to_parse))
        with concurrent.futures.ThreadPoolExecutor(max_workers=feed_workers) as executor:
            # Submit all feed parsing tasks
            future_to_feed = {executor.submit(parse_feed, feed_url): feed_url for feed_url in feed_urls_to_parse}
            for future in concurrent.futures.as_completed(future_to_feed):
                feed_url = future_to_feed[future]
                try:
                    urls_from_single_feed = future.result()
                    if urls_from_single_feed:
                        urls_from_all_feeds.update(urls_from_single_feed)
                        logging.info(f"Successfully parsed {feed_url}, found {len(urls_from_single_feed)} URLs.")
                    else:
                         logging.warning(f"No URLs extracted from feed: {feed_url}")
                except Exception as exc:
                    logging.error(f'Feed {feed_url} generated an exception during parsing: {exc}')
        # Combine URLs from args and feeds
        initial_urls_to_scrape = initial_urls_from_args.union(urls_from_all_feeds)
    else:
        initial_urls_to_scrape = initial_urls_from_args

    # --- Setup for Staged Crawling --- 
    processed_urls = set() # Keep track of all URLs processed across depths
    scrape_results = {} # Store content_area results {url: content_area_soup_object}
    processed_urls_lock = threading.Lock() # Lock for accessing shared sets/dicts

    urls_to_process_this_depth = list(initial_urls_to_scrape)
    current_depth = 0

    # Adjust max_depth based on --crawl flag: 0 means only initial, 1 means initial+links, etc.
    effective_max_depth = args.max_depth if args.crawl else 0

    # --- Main Crawl Loop --- 
    while urls_to_process_this_depth and current_depth <= effective_max_depth:
        logging.info(f"--- Starting scrape for Depth {current_depth} ({len(urls_to_process_this_depth)} URLs) --- ")
 
        # URLs found in this stage that produced content, used for link finding next
        successfully_scraped_this_depth = set()

        # Use ThreadPoolExecutor for parallel scraping at this depth
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_url = {executor.submit(scrape_and_process, url, args.output_dir, args.user_agent, processed_urls_lock, scrape_results): url
                           for url in urls_to_process_this_depth}
 
            successfully_scraped_this_depth = []
            for future in concurrent.futures.as_completed(future_to_url):
                original_url = future_to_url[future]
                try:
                    processed_url_result = future.result() # Returns URL on success, None on failure/skip
                    if processed_url_result: # Check if the result is not None
                        successfully_scraped_this_depth.append(processed_url_result)
                        # Note: Link finding later will use scrape_results, which only contains HTML results
                except Exception as exc:
                    logging.error(f'URL {original_url} (Depth {current_depth}) generated an exception during scraping: {exc}')

        logging.info(f"--- Finished scraping for Depth {current_depth} --- ")

        # --- Find links for the next depth (if crawling) --- 
        next_urls_to_process = set()
        logging.info(f"Finding sub-links from Depth {current_depth} results ({len(successfully_scraped_this_depth)} pages)...")
        
        # Sequentially process results from the completed depth to find links for the next
        for parent_url in successfully_scraped_this_depth:
            # Retrieve stored results (content_area for crawling, document_urls for direct links)
            result_tuple = scrape_results.get(parent_url)
 
            # Initialize lists for links from this parent
            links_from_this_parent = []
            content_area_for_crawl = None

            if result_tuple:
                 content_area_for_crawl, extracted_document_urls = result_tuple
                 # Add explicitly found document URLs first
                 links_from_this_parent.extend(extracted_document_urls)
            # else: It was likely a PDF download, which has no tuple in scrape_results
            # Or the scrape failed for this parent_url

            # If crawling is enabled and we have content, find general sub-links
            if args.crawl and content_area_for_crawl:
                 sub_links = find_sub_links(parent_url, content_area_for_crawl)
                 links_from_this_parent.extend(sub_links)
            elif args.crawl and not content_area_for_crawl and result_tuple:
                 # HTML scrape succeeded, but content area is null (should be rare if scrape succeeded)
                 logging.debug(f"Crawling enabled, but no content_area found for {parent_url} to find sub-links.")

            # Filter and add unique links found from this parent URL
            if links_from_this_parent:
                 parent_domain = urlparse(parent_url).netloc
                 for link in set(links_from_this_parent): # Use set to process unique links from this parent
                     # Apply domain restriction if needed
                     if args.same_domain:
                         link_domain = urlparse(link).netloc
                         if link_domain != parent_domain:
                             logging.debug(f"Skipping different domain link: {link} (parent: {parent_url})")
                             continue

                     # Check if already processed (thread-safe check)
                     with processed_urls_lock: # Re-acquire lock briefly to update results
                         if link not in processed_urls:
                             # Check again right before adding to prevent duplicates if found concurrently in link finding
                             if link not in next_urls_to_process:
                                 next_urls_to_process.add(link)

        if not next_urls_to_process:
            logging.info(f"No new, valid, unprocessed URLs found for Depth {current_depth + 1}. Stopping crawl.")
            break

        # Prepare for the next iteration
        urls_to_process_this_depth = list(next_urls_to_process)
        current_depth += 1

        # Clear results from previous depth to save memory (optional)
        scrape_results.clear()

    logging.info(f"Scraping process completed. Processed {len(processed_urls)} unique URLs in total up to depth {current_depth}.")

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

def scrape_and_process(url, output_dir, user_agent, processed_urls_lock, scrape_results):
    # Lock released, now perform I/O
    try:
        # --- Check if URL is a PDF --- 
        parsed_target_url = urlparse(url)
        # Check the path component for the extension
        if parsed_target_url.path and parsed_target_url.path.lower().endswith('.pdf'):
            logging.debug(f"Identified PDF: {url}. Attempting direct download.")
            # Call the dedicated download function
            success_url = download_binary_file(url, output_dir, user_agent)
            # PDFs don't have 'content_area' for link finding, so nothing added to scrape_results
            return success_url # Returns URL on success, None on failure
        else:
            # --- Process as HTML page --- 
            logging.debug(f"Processing as HTML: {url}")
            content_area, document_urls = scrape_content(url, output_dir, user_agent)
            if content_area:
                # Store result for potential later link finding (needs lock)
                with processed_urls_lock: # Re-acquire lock briefly to update results
                    scrape_results[url] = (content_area, document_urls) # Store the tuple
                return url # Return URL on success
            else:
                # Failed to scrape HTML content
                return None # Indicate failure
    except Exception as e:
        logging.error(f"Error processing URL {url} in thread: {e}")
        # No need to manually release lock here, `with` handles it on exit/exception
        return None # Indicate failure

if __name__ == "__main__":
    main()
