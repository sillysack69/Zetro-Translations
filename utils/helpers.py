"""
Shared helpers: fetching soup with retries, parsing range selection, image handling helpers.
"""

import logging
import time
from typing import List, Tuple, Any
import requests
from bs4 import BeautifulSoup
import re

logger = logging.getLogger("epub_downloader.helpers")


def fetch_soup(url: str, retries: int = 3, backoff: float = 1.0) -> BeautifulSoup:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            logger.debug("GET %s (attempt %d)", url, attempt)
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            return BeautifulSoup(r.content, "lxml")
        except Exception as e:
            last_exc = e
            logger.warning("Request failed (%s). Retrying in %.1fs...", e, backoff)
            time.sleep(backoff)
            backoff *= 2
    logger.error("Failed to fetch URL: %s", url)
    raise last_exc


def parse_range_selection(items: List[Tuple[str, Any]], selection: str) -> List[Tuple[str, Any]]:
    """
    selection: '1', '1-5', 'all'
    items: list of (title, link) in current order
    returns sublist
    """
    total = len(items)
    if selection is None or selection.lower() == "all":
        return items[:]
    selection = selection.strip()
    if re.match(r'^\d+$', selection):
        idx = int(selection) - 1
        if idx < 0 or idx >= total:
            raise IndexError("Chapter index out of range")
        return [items[idx]]
    m = re.match(r'^(\d+)-(\d+)$', selection)
    if m:
        start = int(m.group(1)) - 1
        end = int(m.group(2))
        if start < 0:
            start = 0
        if end > total:
            end = total
        if start >= end:
            raise IndexError("Invalid chapter range")
        return items[start:end]
    raise ValueError("Invalid range syntax. Use 'all', 'N', or 'N-M'.")
