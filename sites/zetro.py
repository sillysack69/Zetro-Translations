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
    if ':' in translator:
        translator = translator.split(':')[1]

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

    alt = soup.find('h5', string=lambda t: t and "Alternative" in t)
    alternate = alt.find_parent(class_='post-content_item').find('div', class_='summary-content').get_text(strip=True) if alt and alt.find_parent(class_='post-content_item') else None

    meta = {
        "title": title,
        "alternate": alternate,
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


from bs4 import BeautifulSoup, NavigableString, Tag
import re

def fetch_chapter_paragraphs(chapters_toc: dict, selection: str) -> List[Tuple[str, list]]:
    selected = parse_range_selection(list(chapters_toc.items()), selection)
    all_chapters = []

    def iter_blocks(node):
        for child in node.children:
            if isinstance(child, Tag):
                if child.name in ('p', 'img'):
                    yield child
                else:
                    yield from iter_blocks(child)

    def is_ad_image(src: str) -> bool:
        if not src:
            return True
        src_l = src.lower()
        ad_keywords = ("banner_zetrofm", "kofi", "ko-fi", "/ads/")
        return any(x in src_l for x in ad_keywords)

    for title, link in selected:
        logger.info("Downloading %s", title)
        soup = fetch_soup(link)

        content_wrapper = soup.find('div', {'class': 'entry-content_wrap'})
        container = None
        if content_wrapper:
            rc = content_wrapper.find(
                lambda tag: tag.name == 'div' and (
                    'reading-content' in tag.get('class', []) or
                    'text-left' in tag.get('class', [])
                ),
                recursive=True
            )
            if rc:
                container = rc

        cleaned = []
        title_lower = title.lower()

        # Step 1 — grab top-level images/captions before reading content
        if content_wrapper:
            pre_body_blocks = []
            for elem in content_wrapper.children:
                if container and elem == container:
                    break  # stop before the main body
                if isinstance(elem, Tag) and elem.name in ('p', 'img'):
                    pre_body_blocks.append(elem)
            for block in pre_body_blocks:
                if block.name == 'p':
                    imgs = [str(img) for img in block.find_all('img') if not is_ad_image(img.get('src', ''))]
                    text = block.get_text(strip=True)
                    if imgs or text:
                        cleaned.append(BeautifulSoup(f"<p>{''.join(imgs)} {text}</p>", 'lxml').p)
                elif block.name == 'img':
                    if not is_ad_image(block.get('src', '')):
                        cleaned.append(BeautifulSoup(f"<p>{str(block)}</p>", 'lxml').p)

        # Step 2 — parse main body if available
        if container:
            blocks = list(iter_blocks(container))
            skip_next_caption = False
            for i, node in enumerate(blocks):
                if node.name == 'p':
                    text_buffer = []
                    imgs_in_p = []
                    for part in node.contents:
                        if isinstance(part, Tag) and part.name == 'img':
                            src = part.get('src', '')
                            if not is_ad_image(src):
                                imgs_in_p.append(str(part))
                        else:
                            txt = part.get_text(separator=' ', strip=True) if isinstance(part, Tag) else str(part).strip()
                            if txt:
                                text_buffer.append(txt)

                    combined_text = " ".join(text_buffer).strip()

                    if combined_text:
                        if re.match(r'^_+$', combined_text) or re.match(r'^ー+$', combined_text) or re.match(r'\xa0', combined_text) or re.match(r'TL: SHINIGAMI-san', combined_text) or re.match(r'\bChapter\s*\d+', combined_text, re.IGNORECASE):
                            continue
                        if combined_text.lower() == title_lower:
                            continue

                    if imgs_in_p:
                        html_content = "".join(imgs_in_p)
                        if combined_text:
                            html_content += " " + combined_text
                        cleaned.append(BeautifulSoup(f"<p>{html_content}</p>", 'lxml').p)
                        continue

                    if combined_text:
                        cleaned.append(BeautifulSoup(f"<p>{combined_text}</p>", 'lxml').p)

                elif node.name == 'img':
                    src = node.get('src', '')
                    if is_ad_image(src):
                        continue
                    caption = ""
                    if i + 1 < len(blocks) and blocks[i + 1].name == 'p':
                        possible_caption = blocks[i + 1].get_text(strip=True)
                        if possible_caption and not re.match(r'^_+$', possible_caption) and not re.match(r'^ー+$', possible_caption):
                            caption = " " + possible_caption
                            skip_next_caption = True
                    cleaned.append(BeautifulSoup(f"<p>{str(node)}{caption}</p>", 'lxml').p)

                if skip_next_caption:
                    skip_next_caption = False
                    continue

        all_chapters.append((title, cleaned))

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
    builder.set_translator(meta.get('translator'))
    builder.set_genres(meta.get('genres'))
    builder.set_alternate_title(meta.get("alternate"))
    builder.set_extra_links(meta.get('links'))
    if meta.get("cover"):
        builder.set_cover_url(meta.get("cover"))
    builder.add_chapters(chapters)
    builder.build(save_as)
