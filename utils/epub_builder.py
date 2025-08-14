"""
EpubBuilder: unified EPUB creation with site-specific options.

Now with:
 - optional cover download and inclusion
 - optional cover-as-first-page in spine
 - insertion of intro page (with synopsis & metadata)
 - adding chapters (list of (title, list_of_bs4_tags_or_strings))
 - automatic downloading and embedding of chapter images
"""

from ebooklib import epub
import uuid
from typing import List, Tuple, Optional
import logging
from io import BytesIO
from PIL import Image
import requests
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger("epub_downloader.epub_builder")


class EpubBuilder:
    def __init__(self, title: str, author: Optional[str] = None, language: str = "en",
                 include_cover_page: bool = True, cover_first_in_spine: bool = True):
        self.title = title or "Untitled"
        self.author = author or ""
        self.language = language
        self.include_cover_page = include_cover_page
        self.cover_first_in_spine = cover_first_in_spine

        self._chapters: List[Tuple[str, List]] = []
        self._cover_url: Optional[str] = None
        self._synopsis: Optional[str] = None
        self._alternate_title: Optional[str] = None
        self._extra_links: Optional[List[dict]] = None
        self._genres: Optional[str] = None
        self._translator: Optional[str] = None

        # New for image embedding
        self._images = {}
        self._image_counter = 1

    def set_cover_url(self, url: str):
        self._cover_url = url

    def set_synopsis(self, synopsis: str):
        self._synopsis = synopsis

    def set_genres(self, genres: str):
        self._genres = genres

    def set_translator(self, translator: str):
        self._translator = translator

    def set_alternate_title(self, alt: str):
        self._alternate_title = alt

    def set_extra_links(self, links: List[dict]):
        self._extra_links = links

    def add_chapters(self, chapters: List[Tuple[str, List]]):
        """
        chapters: list of (title, list_of_bs4_tag_or_string)
        """
        self._chapters.extend(chapters)

    def _download_and_prepare_cover(self) -> Optional[bytes]:
        if not self._cover_url:
            logger.debug("No cover URL provided.")
            return None
        try:
            logger.info("Downloading cover image ...")
            r = requests.get(self._cover_url, timeout=20)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=98)
            return buf.getvalue()
        except Exception as e:
            logger.warning("Failed to download/process cover: %s", e)
            return None

    def _download_image(self, url: str) -> Optional[bytes]:
        """Download image and convert to JPEG bytes."""
        try:
            logger.info("Downloading image: %s", url)
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=98)
            return buf.getvalue()
        except Exception as e:
            logger.warning("Failed to download image %s: %s", url, e)
            return None

    def _process_chapter_images(self, html_content: str, base_url: Optional[str] = None) -> str:
        """Finds <img> tags, downloads them, and replaces src with local paths."""
        soup = BeautifulSoup(html_content, "html.parser")
        for img_tag in soup.find_all("img"):
            src = img_tag.get("src")
            src = (src or '').split('?')[0]

            if not src:
                continue
            abs_url = urljoin(base_url, src) if base_url else src
            img_bytes = self._download_image(abs_url)
            if not img_bytes:
                continue
            img_id = f"img_{self._image_counter}"
            self._image_counter += 1
            filename = f"images/{img_id}.jpg"
            # Store image bytes for later adding to EPUB
            self._images[filename] = img_bytes
            # Replace src in HTML
            img_tag["src"] = f"../{filename}"
        return str(soup)

    def build(self, output_basename: str):
        book = epub.EpubBook()
        book.set_identifier(str(uuid.uuid4()))
        book.set_title(self.title)
        book.set_language(self.language)
        if self.author:
            book.add_author(self.author, role="aut", uid="author")
        if self._translator:
            book.add_author(self._translator, role="tlr", uid="translator")
        if self._synopsis:
            book.add_metadata('DC', 'description', self._synopsis)
        if self._alternate_title:
            book.add_metadata('DC', 'alternative', self._alternate_title)
        if self._genres:
            book.add_metadata('DC', 'subject', self._genres)

        # stylesheet
        css = """
        h1 { margin-bottom: 2em; }
        h2 { margin-top: 2em; margin-bottom: 2em; }
        p { text-indent: 0; margin-top: 1.4em; margin-bottom: 1.4em; }
        hr { border: none; border-top: 2px solid #ccc; margin: 2em 0; }
        img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
        """
        style = epub.EpubItem(uid="style_nav", file_name="styles/style.css", media_type="text/css", content=css)
        book.add_item(style)

        cover_content = None
        coverpage = None
        if self._cover_url and self.include_cover_page:
            cover_content = self._download_and_prepare_cover()
            if cover_content:
                image = epub.EpubImage(uid="cover", file_name="images/cover.jpg", media_type="image/jpeg", content=cover_content)
                book.add_item(image)
                coverpage = epub.EpubHtml(title='Cover', file_name='xhtml/cover.xhtml', lang=self.language)
                coverpage.content = f'<img src="../images/cover.jpg" alt="Cover" style="max-width: 100%; height: auto;" />'
                book.add_item(coverpage)

        # intro page
        intro = epub.EpubHtml(title='Introduction', file_name='xhtml/intro.xhtml', lang=self.language)
        links_html = ""
        if self._extra_links:
            links_html = "<h3>Links</h3><ul>" + "".join(
                f'<li><a href="{link["href"]}" target="_blank">{link["text"]}</a></li>'
                for link in self._extra_links if link.get("href")
            ) + "</ul>"
        intro_content = f"<h1>{self.title}</h1>"
        if self._alternate_title:
            intro_content += f"<h3>Alternate Title: {self._alternate_title}</h3>"
        if self.author:
            intro_content += f"<h3>Author: {self.author}</h3>"
        if self._translator:
            intro_content += f"<h3>Translator: {self._translator}</h3>"
        if self._synopsis:
            intro_content += f"<p><strong>Synopsis:</strong> {self._synopsis}</p>"
        intro_content += links_html
        intro.content = intro_content
        intro.add_link(href='../styles/style.css', rel='stylesheet', type='text/css')
        book.add_item(intro)

        # chapters
        chapter_items = []
        for idx, (title, paras) in enumerate(self._chapters, start=1):
            chap = epub.EpubHtml(title=title, file_name=f'xhtml/chap_{idx}.xhtml', lang=self.language)
            body_html = "".join(str(p) for p in paras) if paras else ""
            body_html = self._process_chapter_images(body_html)  # process images
            chap.content = f"<h2>{title}</h2>" + body_html + "<hr>"
            chap.add_link(href='../styles/style.css', rel='stylesheet', type='text/css')
            book.add_item(chap)
            chapter_items.append(chap)

        # Add all downloaded images to the EPUB
        for filename, content in self._images.items():
            img_item = epub.EpubImage(uid=filename, file_name=filename, media_type="image/jpeg", content=content)
            book.add_item(img_item)

        # TOC
        toc_list = []
        if coverpage:
            toc_list.append(epub.Link('xhtml/cover.xhtml', 'Cover', 'cover'))
        toc_list.append(epub.Link('xhtml/intro.xhtml', 'Introduction', 'intro'))
        toc_list.extend(chapter_items)
        book.toc = tuple(toc_list)

        # nav
        nav = epub.EpubNav(file_name='xhtml/nav.xhtml')
        nav.add_link(href='../styles/style.css', rel='stylesheet', type='text/css')
        book.add_item(nav)

        # spine ordering
        spine = []
        if self.cover_first_in_spine and coverpage:
            spine.append(coverpage)
        spine.append(nav)
        spine.append(intro)
        spine.extend(chapter_items)
        book.spine = spine

        # navigation files
        book.add_item(epub.EpubNcx())

        output_file = output_basename if output_basename.endswith('.epub') else output_basename + '.epub'
        logger.info("Generating EPUB: %s", output_file)
        epub.write_epub(output_file, book)
        logger.info("Saved EPUB: %s", output_file)
