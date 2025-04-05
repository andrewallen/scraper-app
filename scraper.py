import argparse
import os
import logging
import concurrent.futures
import threading
from typing import Set, Dict
from urllib.parse import urlparse

# Import necessary functions from the new modules
from scraper_app.parse_feed import parse_feed
from scraper_app.parse_html import parse_and_save_html, find_sub_links
from scraper_app.storage import download_binary_file
from scraper_app.constants import (
    DEFAULT_USER_AGENT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_MAX_DEPTH,
    DEFAULT_WORKERS
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scrape_and_process(
    url: str,
    output_dir: str,
    user_agent: str,
    processed_urls_lock: threading.Lock,
    processed_urls: Set[str],
    crawl_enabled: bool,
    max_depth: int,
    current_depth: int,
    same_domain_only: bool,
    executor: concurrent.futures.ThreadPoolExecutor,
    pending_futures: Dict[concurrent.futures.Future, Dict]
) -> None:
    """Scrapes a single URL, processes its content and documents, and potentially queues sub-links."""
    logging.info(f"[Depth {current_depth}] Processing page: {url}")

    # Scrape HTML page, save markdown, get content soup and document links
    content_area_soup, document_urls = parse_and_save_html(url, output_dir, user_agent)

    # --- Download linked documents discovered on the page ---
    for doc_url in document_urls:
        should_process_doc = False
        with processed_urls_lock:
            if doc_url not in processed_urls:
                processed_urls.add(doc_url)
                should_process_doc = True

        if should_process_doc:
            logging.info(f"Queueing document download: {doc_url}")
            future = executor.submit(download_binary_file, doc_url, output_dir, user_agent)
            pending_futures[future] = {'url': doc_url, 'type': 'document'} # Track future
        else:
            logging.debug(f"Skipping already processed document: {doc_url}")

    # --- Crawl Sub-links found on the page ---
    if crawl_enabled and current_depth < max_depth and content_area_soup:
        sub_links = find_sub_links(url, content_area_soup)
        logging.info(f"Found {len(sub_links)} potential sub-links on {url}")

        base_domain = urlparse(url).netloc

        for sub_link in sub_links:
             # Apply same-domain filter if enabled
            if same_domain_only and urlparse(sub_link).netloc != base_domain:
                 logging.debug(f"Skipping sub-link (different domain): {sub_link}")
                 continue

            should_process_sublink = False
            with processed_urls_lock:
                if sub_link not in processed_urls:
                    processed_urls.add(sub_link)
                    should_process_sublink = True

            if should_process_sublink:
                logging.info(f"Queueing sub-link crawl (depth {current_depth + 1}): {sub_link}")
                # Submit sub-link scraping to the executor
                future = executor.submit(
                    scrape_and_process, # Recursive call
                    sub_link, output_dir, user_agent,
                    processed_urls_lock, processed_urls,
                    crawl_enabled, max_depth, current_depth + 1, same_domain_only,
                    executor, pending_futures
                )
                pending_futures[future] = {'url': sub_link, 'type': 'page', 'depth': current_depth + 1} # Track future
            else:
                logging.debug(f"Skipping already processed sub-link: {sub_link}")


def main() -> None:
    # Determine default workers based on CPU count, with a fallback
    try:
         cpu_workers = os.cpu_count()
         calculated_workers = min(32, cpu_workers + 4 if cpu_workers else DEFAULT_WORKERS)
    except NotImplementedError:
         calculated_workers = DEFAULT_WORKERS

    parser = argparse.ArgumentParser(
        description="Scrape content from gov.uk URLs or feeds, convert to Markdown, save attachments, and optionally crawl sub-pages.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Input source group
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('urls', nargs='*', help="One or more gov.uk URLs to scrape (if no feed options used).")
    input_group.add_argument('--feed-url', help="URL of a single RSS/Atom feed to process.")
    input_group.add_argument('--feed-file', help="Path to a text file containing multiple feed URLs (one per line).")

    # Output and Request options
    parser.add_argument('-o', '--output-dir', default=DEFAULT_OUTPUT_DIR, help="Directory to save the resulting files.")
    parser.add_argument('--user-agent', default=DEFAULT_USER_AGENT, help="Custom User-Agent string for HTTP requests.")

    # Crawling options
    parser.add_argument('--crawl', action='store_true', help="Enable crawling of relevant sub-links found on scraped pages.")
    parser.add_argument('--max-depth', type=int, default=DEFAULT_MAX_DEPTH, help="Maximum crawl depth (0=initial URLs only, 1=initial+1 level, etc.).")
    parser.add_argument('--same-domain', action='store_true', help="When crawling, only follow links on the *exact* same domain as the source page.")

    # Performance options
    parser.add_argument('-w', '--workers', type=int, default=calculated_workers, help="Number of parallel workers (threads) for scraping/downloading.")

    args = parser.parse_args()

    # Validate crawl options
    if (args.max_depth < 0):
        parser.error("--max-depth cannot be negative.")

    # If crawl is not enabled, adjust effective depth for clarity
    effective_max_depth = args.max_depth if args.crawl else 0

    # --- Determine Initial URLs ---
    initial_urls: Set[str] = set() # Use set to auto-deduplicate
    if args.urls:
        initial_urls.update(args.urls)
    elif args.feed_url:
        initial_urls.update(parse_feed(args.feed_url))
    elif args.feed_file:
        try:
            with open(args.feed_file, 'r') as f:
                feed_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            # Parse feeds in parallel for efficiency
            feed_parse_workers = min(args.workers, len(feed_urls))
            with concurrent.futures.ThreadPoolExecutor(max_workers=feed_parse_workers) as feed_executor:
                 future_to_feed_url = {feed_executor.submit(parse_feed, url): url for url in feed_urls}
                 for future in concurrent.futures.as_completed(future_to_feed_url):
                      feed_url_origin = future_to_feed_url[future]
                      try:
                           urls_from_feed = future.result()
                           initial_urls.update(urls_from_feed)
                      except Exception as exc:
                           logging.error(f"Failed to parse feed {feed_url_origin}: {exc}")
        except FileNotFoundError:
            logging.error(f"Feed file not found: {args.feed_file}")
            return
        except IOError as e:
             logging.error(f"Error reading feed file {args.feed_file}: {e}")
             return

    if not initial_urls:
        logging.warning("No valid initial URLs found to process.")
        return

    logging.info(f"Starting scrape process with {len(initial_urls)} unique initial URLs.")
    logging.info(f"Output directory: {args.output_dir}")
    logging.info(f"Crawling enabled: {args.crawl}, Effective max depth: {effective_max_depth}, Same domain only: {args.same_domain}")
    logging.info(f"Number of workers: {args.workers}")

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    # --- Setup for Parallel Processing ---
    processed_urls: Set[str] = set() # Shared set to track processed URLs (pages and documents)
    processed_urls_lock = threading.Lock() # Lock for safe concurrent access to the set
    # Dictionary to keep track of futures -> {url, type, depth} mapping for logging results
    pending_futures: Dict[concurrent.futures.Future, Dict] = {}

    # Using ThreadPoolExecutor for I/O bound tasks (network requests)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit initial URLs for scraping
        for url in initial_urls:
            should_process = False
            with processed_urls_lock:
                if url not in processed_urls:
                    processed_urls.add(url)
                    should_process = True

            if should_process:
                logging.debug(f"Queueing initial URL: {url}")
                future = executor.submit(
                    scrape_and_process,
                    url, args.output_dir, args.user_agent,
                    processed_urls_lock, processed_urls,
                    args.crawl, effective_max_depth, 0, args.same_domain, # Start at depth 0
                    executor, pending_futures
                )
                pending_futures[future] = {'url': url, 'type': 'page', 'depth': 0} # Track future
            else:
                logging.info(f"Skipping duplicate initial URL: {url}")

        # --- Wait for all tasks to complete ---
        completed_count = 0
        total_tasks = len(pending_futures)
        logging.info(f"Waiting for {total_tasks} initial tasks (and any spawned sub-tasks) to complete...")

        # Process completed futures as they finish
        # Keep track of completed futures to avoid processing them again if new ones are added during iteration
        processed_futures = set()
        while len(processed_futures) < len(pending_futures):
            # Get newly completed futures since the last check
            newly_completed = {f for f in concurrent.futures.as_completed(pending_futures) if f not in processed_futures}

            for future in newly_completed:
                task_info = pending_futures[future]
                url_processed = task_info['url']
                task_type = task_info.get('type', 'unknown')
                completed_count += 1
                progress = f"({completed_count}/{len(pending_futures)} completed)"

                try:
                    # Get the result - primarily to surface exceptions from the thread
                    result = future.result()

                    if task_type == 'document':
                        if isinstance(result, str):
                            logging.info(f"[OK {progress}] Downloaded document: {url_processed} -> {os.path.basename(result)}")
                        else:
                            # download_binary_file returns None on failure, error already logged
                            logging.warning(f"[Fail {progress}] Failed document download: {url_processed}")
                    elif task_type == 'page':
                         # parse_and_save_html returns (soup, urls), None on critical failure
                         # Success is implicit if no exception occurred
                         logging.info(f"[OK {progress}] Processed page (Depth {task_info.get('depth','?')}): {url_processed}")
                    else:
                         logging.info(f"[OK {progress}] Completed unknown task type for: {url_processed}")

                except Exception as exc:
                    logging.error(f'[Fail {progress}] Task for {task_type} URL {url_processed} generated an exception: {exc}', exc_info=True) # Log traceback

                # Mark this future as processed
                processed_futures.add(future)

            # Update total tasks if new ones were added by completed tasks
            total_tasks = len(pending_futures)
            # Small sleep to prevent busy-waiting if loop is very fast
            if not newly_completed: 
                import time
                time.sleep(0.1)

    logging.info(f"Scraping process finished. Total unique items processed (pages + documents): {len(processed_urls)}")

if __name__ == "__main__":
    main()
