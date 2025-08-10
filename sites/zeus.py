"""
Site module for zeustranslations.blogspot.com
This adapts logic from the zeus script.
"""

from typing import Dict, List, Tuple
import re
import logging
from bs4 import BeautifulSoup
import requests

from utils.helpers import fetch_soup, parse_range_selection
from utils.epub_builder import EpubBuilder

logger = logging.getLogger("epub_downloader.zeus")


def get_label(soup: BeautifulSoup) -> str:
    el = soup.find('div', id='cdrChaptersListSitemap')
    if not el or 'data-label' not in el.attrs:
        raise ValueError("data-label not found on page")
    return el['data-label']


def get_metadata(soup: BeautifulSoup) -> Dict:
    title = soup.find('div', {'class': 'cdr_cover_page--header-title'}).find('h1').get_text(strip=True)
    synopsis_tags = soup.find('div', {'class': 'cdr_cover_page--description'}).find_all('p')
    synopsis = " ".join(str(p) for p in synopsis_tags)
    cover = (soup.find('div', {'class': 'cdr_cover_page--header-thumbnail'}).find('img').get('data-src'))
    if cover and cover.startswith("data:image"):
        cover = None

    info = {"associated_names": None, "author": None, "year": None, "status": None, "links": []}
    for block in soup.select("#extra-info .y6x11p"):
        label_el = block.select_one(".stext")
        if not label_el:
            continue
        label = label_el.get_text(strip=True).lower()
        vals = [el for el in block.find_all("span") if el is not label_el]
        if label == "associated names":
            info["associated_names"] = vals[0].get_text(" ", strip=True) if vals else None
        elif label == "author":
            info["author"] = vals[0].get_text(" ", strip=True) if vals else None
        elif label == "year":
            info["year"] = vals[0].get_text(strip=True) if vals else None
        elif label == "status":
            info["status"] = vals[0].get_text(strip=True) if vals else None
        elif label == "links":
            for a in block.select("a[href]"):
                href = a["href"]
                text = a.get_text(strip=True)
                info["links"].append({"text": text, "href": ('https:' + href) if href.startswith("//") else href})

    # sanitize title like original script
    author_match = re.search(r"\(Author:\s*(.+?)\)", title)
    if not info["author"] and author_match:
        info["author"] = author_match.group(1).strip()
    title_noauthor = re.sub(r"\(Author:\s*.+?\)", "", title, flags=re.IGNORECASE)
    title_cleaned = re.sub(r"\(Chapter[s]?[^)]*\)", "", title_noauthor, flags=re.IGNORECASE)
    title_cleaned = re.sub(r"\s+", " ", title_cleaned).strip()

    meta = {
        "title_noauthor": title_noauthor,
        "title_cleaned": title_cleaned,
        "synopsis": synopsis,
        "alternate": info["associated_names"],
        "year": info["year"],
        "author": info["author"],
        "links": info["links"],
        "status": info["status"],
        "cover": cover,
    }
    return meta


def chapters_toc(data_label: str) -> Dict[str, str]:
    start = 1
    max_results = 150
    chapters_list = {}
    logger.info("Retrieving list of chapters via JSON feed for label %s", data_label)

    while True:
        feed_url = f"https://zeustranslations.blogspot.com/feeds/posts/default/-/{data_label}?alt=json&start-index={start}&max-results={max_results}"
        resp = requests.get(feed_url)
        resp.raise_for_status()
        j = resp.json()
        feed = j.get('feed', {})
        entries = feed.get('entry', [])
        if not entries:
            break
        for e in entries:
            title = e.get('title', {}).get('$t')
            link = next((l.get("href") for l in e.get("link", []) if l.get("rel") == "alternate"), None)
            chapters_list[title] = link
        start += max_results

    reversedchapters = dict(reversed(list(chapters_list.items())))
    # original script removed first element; keep same behavior if exists
    if reversedchapters:
        reversedchapters.popitem()
    return reversedchapters


def chapter_paragraphs(chapters_toc: dict, selection: str) -> List[Tuple[str, list]]:
    selected = parse_range_selection(list(chapters_toc.items()), selection)
    all_chapters = []
    for title, link in selected:
        formatted_title = re.sub(r'^(Chapter\s+\d+)\s+', r'\1: ', title)
        logger.info("Downloading %s", formatted_title)
        soup = fetch_soup(link)
        article = soup.find('article', {'class': 'cdr_chapter_page--content'})
        if not article:
            logger.warning("No article content found for %s", link)
            paras = []
        else:
            paras = article.find_all(['p', 'hr', 'br'])
        all_chapters.append((formatted_title, paras))
    return all_chapters


def run(url: str, range_: str, save_as: str):
    soup = fetch_soup(url)
    label = get_label(soup)
    meta = get_metadata(soup)
    toc = chapters_toc(label)
    chapters = chapter_paragraphs(toc, range_)
    # Zeus original: include cover page only if cover available, and not necessarily first in spine
    builder = EpubBuilder(
        title=meta.get("title_cleaned"),
        author=meta.get("author"),
        language="en",
        include_cover_page=bool(meta.get("cover")),
        cover_first_in_spine=False
    )
    builder.set_synopsis(meta.get("synopsis"))
    builder.set_alternate_title(meta.get("alternate"))
    if meta.get("cover"):
        builder.set_cover_url(meta.get("cover"))
    # include external links in intro notes
    builder.set_extra_links(meta.get("links"))
    builder.add_chapters(chapters)
    builder.build(save_as)
