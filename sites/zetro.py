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
    title = soup.find('h1').text.strip() if soup.find('h1') else "Untitled"

    author_tag = soup.find('div', {'class': 'author-content'})
    author = author_tag.get_text(strip=True) if author_tag else ""

    translator_tag = soup.find('div', {'class': 'artist-content'})
    translator = translator_tag.get_text(strip=True) if translator_tag else ""

    synopsis_div = soup.find('div', {'class': 'summary__content show-more'})
    synopsis_html = ""

    if synopsis_div:
        # Remove unwanted tags fully
        for tag in synopsis_div.find_all(['h1', 'h2', 'blockquote', 'a']):
            tag.decompose()

        # Unwrap all <span> tags (keep text, remove tag)
        for span in synopsis_div.find_all('span'):
            span.unwrap()

        allowed_parts = []
        for elem in synopsis_div.children:
            # If it's a <p> tag
            if getattr(elem, "name", None) == 'p':
                text = elem.get_text(strip=True)
                if any(phrase in text for phrase in ["Next unlock", "Like what I do"]):
                    continue
                allowed_parts.append(str(elem))
            # If it's a NavigableString or text node (no .name)
            elif isinstance(elem, str) or elem.name is None:
                text = str(elem).strip()
                if text and not any(phrase in text for phrase in ["Next unlock", "Like what I do"]):
                    # Wrap bare text in <p> for consistency
                    allowed_parts.append(f"<p>{text}</p>")
            # Ignore other tags

        # Join all allowed parts
        synopsis_html = "".join(allowed_parts)

        # Add trailing period inside last paragraph if needed
        if allowed_parts:
            last_p_text = BeautifulSoup(allowed_parts[-1], 'html.parser').get_text().strip()
            if last_p_text and last_p_text[-1].isalpha() and not last_p_text.endswith('.'):
                allowed_parts[-1] = allowed_parts[-1][:-4] + '.' + '</p>'
                synopsis_html = "".join(allowed_parts)

    genres_tag = soup.find('div', {'class': 'genres-content'})
    genres = genres_tag.get_text(strip=True) if genres_tag else ""

    cover_tag = soup.find('div', {'class': 'summary_image'})
    cover = cover_tag.find('img')['src'].split('?')[0] if cover_tag and cover_tag.find('img') else None

    meta = {
        "title": title,
        "author": author,
        "translator": translator,
        "synopsis": synopsis_html,
        "genres": genres,
        "cover": cover,
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
                return f"Chapter {chap_num}"
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
                        or re.match(r'\bChapter\s*\d+', text, re.IGNORECASE)
                        or re.match(r'[ー\-\s―]+', text)
                   ):
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
