"""Handles parsing of RSS/Atom feeds to extract article URLs."""

import logging
import feedparser
from typing import List

def parse_feed(feed_url: str) -> List[str]:
    """Parses an RSS/Atom feed and returns a list of article URLs.

    Given a URL of an RSS or Atom feed, this function uses the feedparser library
    to parse the feed and return a list of URLs for the articles described in the
    feed. If the feed is ill-formed or cannot be parsed for any other reason, a
    warning is logged and an empty list is returned.
    """
    urls: List[str] = []
    try:
        logging.info(f"Parsing feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        if feed.bozo:
             exception_info = ""
             if isinstance(feed.bozo_exception, Exception):
                 exception_info = f": {feed.bozo_exception}"
             elif feed.bozo_exception:
                 exception_info = f": {feed.bozo_exception}"
             logging.warning(f"Feed {feed_url} may be ill-formed{exception_info}")

        for entry in feed.entries:
            if hasattr(entry, 'link'):
                urls.append(entry.link)
            else:
                logging.warning(f"Feed entry in {feed_url} missing link attribute: {entry.get('title', 'No Title')}")

        logging.info(f"Found {len(urls)} entries in feed: {feed_url}")
        return urls
    except Exception as e:
        logging.error(f"Failed to parse feed {feed_url}: {e}")
        return []
