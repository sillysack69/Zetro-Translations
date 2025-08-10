# Modular EPUB Downloader

A modular Python program for scraping novels from multiple translation/blog sites and producing EPUB files.  
This repository currently supports:

- **zetrotranslation.com**
- **zeustranslations.blogspot.com**

Each site's scraping logic is isolated in `sites/<site>.py`. Common EPUB creation utilities are in `utils/epub_builder.py`.

---

## Features

- Modular design — add new site scrapers easily.
- CLI interface (`main.py`) with simple options: `--site`, `--url`, `--range`, `--save`.
- Supports chapter range selection: `1`, `1-5`, `all`.
- Handles optional cover inclusion and site-specific EPUB structure differences.
- Basic retry logic for network requests and graceful logging.

---

## Requirements

- Python 3.9+ recommended
- Install dependencies:

```
pip install -r requirements.txt
```

## Usage

```
python main.py --site zetro --url "https://zetrotranslation.com/novel/..." --range all --save "book-name"
python main.py --site zeus --url "https://zeustranslations.blogspot.com/...html" --range 1-5 --save "book-name"
```

Options:
- `--site` — `zetro` or `zeus`
- `--url` — novel page URL
- `--range` — `all` (default), single index (`5`), or range (`1-10`)
- `--save` — filename (without `.epub`)
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
3. Add the site name to `main.py` `--site` choices (or modify CLI to auto-discover modules in `sites/`).

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
