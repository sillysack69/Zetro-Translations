import requests
from bs4 import BeautifulSoup
import re
from ebooklib import epub
from PIL import Image
from io import BytesIO
import uuid


def mainPageSoup(novelUrl):
	response = requests.get(novelUrl)
	content = response.content
	soup = BeautifulSoup(content, 'lxml')
	return soup

def novelId(soup):
	target = soup.find('div', {'id': 'manga-chapters-holder'})
	novelId = target['data-id']
	return novelId

def bookMetadata(soup):
	title = soup.find('h1').text.strip()
	author = soup.find('div', {'class': 'author-content'}).text.strip()
	translator = soup.find('div', {'class': 'artist-content'}).text.strip()
	synopsis = soup.find('div', {'class': 'summary__content show-more'}).text.strip()
	genres = soup.find('div', {'class': 'genres-content'}).text.strip()
	cover = soup.find('div', {'class': 'summary_image'}).find('img')['src'].split('?')[0]
	metadata = {'title': title,
				'author': author,
				'translator': translator,
				'synopsis': synopsis,
				'genres': genres,
				'cover': cover
	}
	return metadata

def getChapters(Id):
	urlchapters = 'https://zetrotranslation.com/wp-admin/admin-ajax.php'

	data = {
		'action': 'manga_get_chapters',
		'manga': Id
	}

	response = requests.post(urlchapters, data=data)
	content = response.content
	return content

def normalizeChapterTitle(title):
    match = re.match(r'(?:Chapter\s*)?(\d+)[^\w]*(.*)', title.strip(), re.IGNORECASE)
    if match:
        chap_num = int(match.group(1))
        chap_title = match.group(2).strip()

        # Remove surrounding parentheses or weird characters
        chap_title = re.sub(r'^[\(\[\-\s]*', '', chap_title)
        chap_title = re.sub(r'[\)\]\s]*$', '', chap_title)

        # Default title if empty
        if not chap_title:
            chap_title = "Untitled"

        return f"Chapter {chap_num} - {chap_title}"

    # If no match, return the raw title as a fallback
    return title.strip()

def chaptersTOC(soup):
	raw = getChapters(novelId(soup))
	soup = BeautifulSoup(raw, 'lxml')
	links = soup.find_all('li')

	chaptersTOC = {}

	for each in links:
		chapterTitle = each.find('a').text
		normalTitle = normalizeChapterTitle(chapterTitle) # clean up chapter title
		chapterLink = each.find('a')['href']
		chaptersTOC[normalTitle] = chapterLink

	chaptersTOC # returns a dictionary
	reversedchaptersTOC = dict(reversed(list(chaptersTOC.items()))) # invert dictionary order
	return reversedchaptersTOC

def chapterParagraphs(chaptersTOC, num):
	dictToList = list(chaptersTOC.items())
	if re.match(r'\d+-\d+', num):
		start, stop = num.split('-')
		selected = dictToList[int(start)-1:int(stop)]
	elif re.match(r'\d+', num):
		selected = [dictToList[int(num)-1]]
	elif re.match(r'all', num):
		selected = dictToList[:]
	else:
		raise ValueError("Invalid chapter range")

	all_chapters = []

	for title, link in selected:
		response = requests.get(link)
		content = response.content
		soup = BeautifulSoup(content, 'lxml')
		paragraph = soup.find('div', {'class': 'entry-content_wrap'}).find_all('p') # list of p tags

		chapter_paragraphs = []

		for p in paragraph:
			text = p.get_text()
			# Skip if only whitespace or non-breaking spaces
			if text != '\xa0' and text != 'TL: SHINIGAMI-san' and not re.match(r'_+', text):
				chapter_paragraphs.append(p)

		all_chapters.append((title, chapter_paragraphs))

	return all_chapters

def coverToJpeg(meta):
	cover_url = meta.get('cover')
	coverImage = requests.get(cover_url).content
	imageBytesWrap = BytesIO(coverImage)
	image = Image.open(imageBytesWrap)
	if image.format == 'PNG':
		image = image.convert('RGB')
	image.save('cover.jpg', quality=95)

def makeEbook(novelName, meta, chapters):
	book = epub.EpubBook()

	# metadata
	book.set_identifier(str(uuid.uuid4()))
	book.set_title(meta.get('title'))
	book.set_language("en")

	"""
	aut → author
	edt → editor
	trl → translator
	ill → illustrator
	"""
	book.add_author(
	    meta.get('author'),
	    role="aut",
	    uid="author",
	)
	book.add_author(
	    meta.get('translator'),
	    role="tlr",
	    uid="translator",
	)
	book.add_metadata('DC', 'description', meta.get('synopsis'))
	genres = meta.get('genres')
	if genres:
		for genre in genres.split(','):
			book.add_metadata('DC', 'subject', genre.strip())

	coverToJpeg(meta) # downloads and saves cover

	book.set_cover('cover.jpg', open('cover.jpg', 'rb').read())

	coverpage = epub.EpubHtml(title='Cover', file_name='cover.xhtml', lang='en')
	coverpage.content = f'''
	<img src="cover.jpg" alt="Cover" style="max-width: 100%; height: auto;" />
	'''
	book.add_item(coverpage)

	intro = epub.EpubHtml(title='Introduction', file_name='intro.xhtml', lang='en')
	intro.content = f'''
	<h1>{meta.get("title")}</h1>
	<h3>Author: {meta.get("author")}</h3>
	<h3>Translator: {meta.get("translator")}</h3>
	<p><strong>Synopsis:</strong> {meta.get("synopsis")}</p>
	'''
	book.add_item(intro)

	chapter_items = []

	for i, (title, paras) in enumerate(chapters):
	    chap = epub.EpubHtml(title=title, file_name=f'chap_{i+1}.xhtml', lang='en')
	    chap.content = f"<h2>{title}</h2>" + ''.join(str(p) for p in paras) + '<hr>'
	    book.add_item(chap)
	    chapter_items.append(chap)

	book.toc = (
		epub.Link('cover.xhtml', 'Cover', 'cover'),
	    epub.Link('intro.xhtml', 'Introduction', 'intro'),
	    *chapter_items
	)

	book.spine = [coverpage, 'nav', intro] + chapter_items

	# Navigation files
	book.add_item(epub.EpubNcx())
	book.add_item(epub.EpubNav())

	epub.write_epub(novelName+'.epub', book)

def main(url, range_, SaveAs):
	soup = mainPageSoup(url)
	toc = chaptersTOC(soup)
	meta = bookMetadata(soup)
	chapters = chapterParagraphs(toc, range_)
	makeEbook(saveAs, meta, chapters)

if __name__== "__main__":
	url1 = 'https://zetrotranslation.com/novel/my-twin-sister-who-looks-exactly-like-me-is-trying-to-cross-the-line-with-me/'
	url2 = 'https://zetrotranslation.com/novel/i-came-to-a-world-where-the-concept-of-chastity-is-reversed-so-i-tried-to-change-my-job-to-a-playboy-but-the-interference-is-intense-please-help-me/'
	range_= '13'
	saveAs = 'nov'
	main(url2,range_,saveAs)