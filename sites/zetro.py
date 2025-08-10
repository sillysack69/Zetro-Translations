"""
Site module for zetrotranslation.com
This file adapts the logic from the original zetrotranslation script.
"""

from typing import Dict, List, Tuple
import re
import logging
from bs4 import BeautifulSoup
import requests

from utils.helpers import fetch_soup, parse_range_selection
from utils.epub_builder import EpubBuilder

logger = logging.getLogger("epub_downloader.zetro")


def novel_id_from_soup(soup: BeautifulSoup) -> str:
    target = soup.find('div', {'id': 'manga-chapters-holder'})
    if not target:
        raise ValueError("Could not find manga-chapters-holder")
    return target['data-id']


def book_metadata(soup: BeautifulSoup) -> Dict:
    title = soup.find('h1').text.strip()
    author = (soup.find('div', {'class': 'author-content'}) or "").get_text(strip=True)
    translator = (soup.find('div', {'class': 'artist-content'}) or "").get_text(strip=True)
    synopsis_div = soup.find('div', {'class': 'summary__content show-more'})
    synopsis = ""
    if synopsis_div:
        for tag in synopsis_div.find_all(['h1', 'h2', 'blockquote', 'a']):
            tag.decompose()
        synopsis = synopsis_div.get_text(strip=True)
    genres = (soup.find('div', {'class': 'genres-content'}) or "").get_text(strip=True)
    cover = (soup.find('div', {'class': 'summary_image'}) or {}).find('img')['src'].split('?')[0] \
        if soup.find('div', {'class': 'summary_image'}) else None
    alternateTitle = None
    summary_content = soup.find_all('div', {'class': 'summary-content'})
    if len(summary_content) >= 3:
        alternateTitle = summary_content[2].get_text(strip=True)
    meta = {
        "title": title,
        "author": author,
        "translator": translator,
        "synopsis": synopsis,
        "genres": genres,
        "cover": cover,
        "alternate": alternateTitle,
    }
    return meta


def get_chapters(novel_id: str) -> str:
    url = 'https://zetrotranslation.com/wp-admin/admin-ajax.php'
    data = {'action': 'manga_get_chapters', 'manga': novel_id}
    resp = requests.post(url, data=data)
    resp.raise_for_status()
    return resp.content


def chapters_toc(soup: BeautifulSoup):
    raw = get_chapters(novel_id_from_soup(soup))
    soup2 = BeautifulSoup(raw, 'lxml')
    links = soup2.find_all('li')
    toc = {}

    def normalize_title(title: str) -> str:
        match = re.match(r'(?:Chapter\s*)?(\d+)[^\w]*(.*)', title.strip(), re.IGNORECASE)
        if match:
            chap_num = int(match.group(1))
            chap_title = match.group(2).strip()
            chap_title = re.sub(r'^[\(\[\-\s]*', '', chap_title)
            chap_title = re.sub(r'[\)\]\s]*$', '', chap_title)
            if not chap_title:
                chap_title = "Untitled"
            return f"Chapter {chap_num}: {chap_title}"
        return title.strip()

    for li in links:
        a = li.find('a')
        if not a:
            continue
        chapter_title = a.get_text(strip=True)
        chapter_link = a.get('href')
        toc[normalize_title(chapter_title)] = chapter_link

    # return reversed order like original script
    reversed_toc = dict(reversed(list(toc.items())))
    return reversed_toc


def fetch_chapter_paragraphs(chapters_toc: dict, selection: str) -> List[Tuple[str, list]]:
    selected = parse_range_selection(list(chapters_toc.items()), selection)
    all_chapters = []

    for title, link in selected:
        logger.info("Downloading %s", title)
        soup = fetch_soup(link)
        content_wrapper = soup.find('div', {'class': 'entry-content_wrap'})
        if not content_wrapper:
            logger.warning("No content wrapper for %s", link)
            paras = []
        else:
            paras = content_wrapper.find_all('p')
            # filter out noise similar to original
            cleaned = []
            for p in paras:
                text = p.get_text()
                if (text.strip() == "" or text == '\xa0'
                        or re.match(r'TL:', text)
                        or re.match(r'_+', text)
                        or re.match(r'\bChapter\s*\d+', text, re.IGNORECASE)):
                    continue
                # cleanup stray underscores after <br> like original
                html_str = str(p)
                html_str = re.sub(r'(<br\s*/?>\s*)_+', '', html_str, flags=re.IGNORECASE)
                cleaned.append(BeautifulSoup(html_str, 'lxml').p)
            paras = cleaned

        all_chapters.append((title, paras))

    return all_chapters


def run(url: str, range_: str, save_as: str):
    """
    Main run function invoked from main.py
    """
    soup = fetch_soup(url)
    meta = book_metadata(soup)
    toc = chapters_toc(soup)
    chapters = fetch_chapter_paragraphs(toc, range_)
    # zetro original always included a cover page and had cover first in the spine
    builder = EpubBuilder(
        title=meta.get("title"),
        author=meta.get("author"),
        language="en",
        include_cover_page=True,
        cover_first_in_spine=True,
    )
    builder.set_synopsis(meta.get("synopsis"))
    builder.set_alternate_title(meta.get("alternate"))
    if meta.get("cover"):
        builder.set_cover_url(meta.get("cover"))
    builder.add_chapters(chapters)
    builder.build(save_as)
