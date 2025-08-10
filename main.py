#!/usr/bin/env python3
"""
CLI entry point for the modular EPUB downloader.

Usage examples:
    python main.py --site zetro --url "https://zetrotranslation.com/novel/..." --range all --save "my_book"
    python main.py --site zeus --url "https://zeustranslations.blogspot.com/..." --range 1-5 --save "my_book"
"""

import argparse
import importlib
import logging
import os
from typing import Tuple

logger = logging.getLogger("epub_downloader")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Modular EPUB downloader for supported sites.")
    p.add_argument("--site", required=True, choices=["zetro", "zeus"], help="Which site scraper to use.")
    p.add_argument("--url", required=True, help="URL of the book/novel page.")
    p.add_argument("--range", default="all", dest="range_", help="Chapter range: e.g. 1, 1-5, all")
    p.add_argument("--save", required=True, help="Output EPUB filename (without .epub).")
    p.add_argument("--outdir", default=".", help="Output directory.")
    p.add_argument("--loglevel", default="INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR).")
    return p.parse_args()


def load_site_module(site_name: str):
    mod = importlib.import_module(f"sites.{site_name}")
    return mod


def ensure_outdir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)


def main():
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.loglevel.upper(), logging.INFO))

    logger.info("Starting EPUB downloader")
    try:
        site_mod = load_site_module(args.site)
    except Exception as e:
        logger.error("Failed to load site module: %s", e)
        return

    outdir = ensure_outdir(args.outdir)
    save_path = os.path.join(outdir, args.save)

    # Each site module exposes a simple `run(url, range_, save_as)` function.
    try:
        site_mod.run(args.url, args.range_, save_path)
        logger.info("Finished. Output: %s.epub", save_path)
    except Exception as exc:
        logger.exception("Error while running scraper: %s", exc)


if __name__ == "__main__":
    main()
