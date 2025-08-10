#!/usr/bin/env python3
"""
CLI entry point for the modular EPUB downloader.

Usage examples:
    python main.py "https://zetrotranslation.com/novel/..." all my_book
    python main.py "https://zeustranslations.blogspot.com/..." 1-5 my_book
"""

import argparse
import importlib
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger("epub_downloader")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

SUPPORTED_SITES = {
    "zetrotranslation.com": "zetro",
    "zeustranslations.blogspot.com": "zeus",
}

def detect_site(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()
    for domain, module_name in SUPPORTED_SITES.items():
        if domain in hostname:
            return module_name
    raise ValueError(f"No scraper available for URL: {url}")


def parse_args():
    p = argparse.ArgumentParser(description="Auto-detecting EPUB downloader for supported sites.")
    p.add_argument("url", help="URL of the book/novel page")
    p.add_argument("range", help="Chapter range: e.g. 1, 1-5, all")
    p.add_argument("save", help="Output EPUB filename (without .epub)")
    p.add_argument("--outdir", default=".", help="Output directory")
    p.add_argument("--loglevel", default="INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR)")
    return p.parse_args()


def load_site_module(site_name: str):
    return importlib.import_module(f"sites.{site_name}")


def ensure_outdir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)


def main():
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.loglevel.upper(), logging.INFO))

    logger.info("Starting EPUB downloader")
    try:
        site_key = detect_site(args.url)
        site_mod = load_site_module(site_key)
        logger.info("Detected site: %s", site_key)
    except Exception as e:
        logger.error("Failed to detect/load site module: %s", e)
        return

    outdir = ensure_outdir(args.outdir)
    save_path = os.path.join(outdir, args.save)

    try:
        site_mod.run(args.url, args.range, save_path)
        logger.info("Finished. Output: %s.epub", save_path)
    except Exception as exc:
        logger.exception("Error while running scraper: %s", exc)


if __name__ == "__main__":
    main()
