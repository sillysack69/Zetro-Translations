# Modular EPUB Downloader

A modular Python program for scraping novels from multiple translation/blog sites and producing EPUB files.  
This repository currently supports:

- **zetrotranslation.com**
- **zeustranslations.blogspot.com**

Each site's scraping logic is isolated in `sites/<site>.py`. Common EPUB creation utilities are in `utils/epub_builder.py`.

---

## Features

- Modular design — add new site scrapers easily.
- CLI interface (`main.py`) with simple options: `<url>`, `<range>`, `<save>`.
- Supports chapter range selection: `1`, `1-5`, `all`.
- Handles optional cover inclusion and site-specific EPUB structure differences.
- Basic retry logic for network requests and graceful logging.

---

## Installation

1. **Clone the repository**
   ```
   git clone https://github.com/sillysack69/Zetro-Translations.git
   cd Zetro-Translations
   ```
2. **(Optional) Create a virtual environment**
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```
4. **Verify installation**
   ```
   python main.py --help
   ```
   If the help text appears, the installation was successful.
   
## Usage
>python main.py `<url>` `<range>` `<save>`
```
python main.py "https://zetrotranslation.com/novel/..." all "book-name"
python main.py "https://zeustranslations.blogspot.com/...html" 1-5 "book-name"
```

Options:
- `<url>` — novel page URL
- `<range>` — `all` (default), single index (`5`), or range (`1-10`)
- `<save>` — filename (without `.epub`)
- `--outdir` — output directory
- `--loglevel` — `DEBUG`, `INFO`, `WARNING`, `ERROR`

## Project structure
```
epub_downloader/
├── main.py
├── requirements.txt
├── README.md
├── sites/
│   ├── zetro.py
│   └── zeus.py
└── utils/
    ├── epub_builder.py
    └── helpers.py
```

- `sites/` — each module implements a `run(url, range_, save_as)` function invoked by `main.py`.
- `utils/epub_builder.py` — unified EPUB builder; accepts options that preserve site-specific behavior.
- `utils/helpers.py` — HTTP fetch, retry, range parsing helpers.

## Adding new sites
1. Create `sites/<newsite>.py`.
2. Implement:
   - `run(url, range_, save_as)` which:
      - fetches page and metadata,
      - produces `chapters: List[(title, paras)]`,
      - constructs `EpubBuilder(...)` with appropriate options,
      - calls `.build(save_as)`.
3. Add the new site's domain and module name to the SUPPORTED_SITES dict. Create a new site module in your sites/ folder, named as the module name you assign. Make sure your new module exposes a run(url, range_, save_as) function matching the interface.

### Example
- Add new site domain and module name to `SUPPORTED_SITES`:
```
SUPPORTED_SITES = {
    "zetrotranslation.com": "zetro",
    "zeustranslations.blogspot.com": "zeus",
    "example.com": "example",         # Add this line
    "another-site.org": "another",   # Add as many as you want
}
```
- Create `sites/example.py` module:
```
def run(url, range_, save_as):
    # Your scraping and EPUB building logic for example.com here
    print(f"Running example.com scraper for {url}")
    # ...
```

## Differences preserved between sites
- **Zetro**: always creates a cover page and places it as the first spine element (original behaviour preserved).
- **Zeus**: only adds a cover page if a valid cover URL exists and keeps it optional in the spine.
These differences are implemented by passing `include_cover_page` and `cover_first_in_spine` flags to the EpubBuilder.

## Troubleshooting
- If pages change layout, selectors may break. Update the relevant site module.
- For large books, network timeouts: increase timeouts or re-run for missing chapters.
- If cover download fails, EPUB will be generated without a cover.

## Contributing
Anyone that can contribute is welcome to expand this library.
