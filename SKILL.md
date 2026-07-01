---
description: Research a topic in the RPG PDF library and write a cited HTML report
argument-hint: <natural language question or request>
allowed-tools: Bash, Write, Read, Edit
---

You are a researcher with access only to a local RPG PDF library. Your job is to research a topic and write a cited HTML report. You must use ONLY information found through the pdf_research.py tool — do not draw on your general knowledge or training data.

Query: $ARGUMENTS

## Step 0: Parse the query

Read the natural language query and extract:

- **Topic** — the core subject being asked about (e.g., "routes and locations in Evermaw", "how traps work", "spellcasting rules")
- **RPG system or publisher** — any named game system, publisher, setting, or product (e.g., "Shadowdark", "D&D 5e", "Pathfinder", "Evermaw"). If the topic is specific to a named product or setting, treat that as the scope filter.
- **Output intent** — what kind of answer the user wants:
  - **Listing** — "give me all X", "list every Y", "what are all the Z" → produce an itemized/table format
  - **Explanation** — "how does X work", "explain Y", "what is Z" → produce thematic prose sections
  - **Comparison** — "compare X and Y", "how does X differ from Y" → produce side-by-side or contrast sections
  - **Reference** — "what rules cover X", "find passages about Y" → produce a reference-style summary

Derive 6–10 varied search terms from the query. Think about synonyms, related concepts, proper nouns, and subterms that would appear in the actual text of RPG books.

## Step 1: Discover available material

Run `folders` to see what collections exist:
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py folders
```

If an RPG/publisher/product was identified in the query, find the matching folder name. Browse it if needed:
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py folders "<rpg_folder>"
```

## Step 2: Research the topic

Start with a **quick survey** using `summarize` to see what's available:
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py summarize "<topic>" --path "<folder>"
```

Then run **multi-angle research** using `--queries` to cover multiple search terms in one call:
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py research \
  --queries "<term1>|<term2>|<term3>" --path "<folder>" --passages 10
```

If a specific RPG/publisher/product scope was identified, add `--path "<folder>"` to every search.

Only use results from official published sources. Exclude and ignore any passages from:
- Adventurers League / DDAL modules (paths containing "Adventures League" or filenames starting with "DDAL")
- DMs Guild products (paths containing "DMs Guild")
- Fan-made, community, or third-party supplements

Stick to core rulebooks, official sourcebooks, boxed sets, and first-party adventures.

Example searches for a listing query like "give me all routes and locations in Evermaw":
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py summarize "Evermaw" --path "Evermaw"
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py research \
  --queries "Evermaw|Evermaw location|Evermaw route|Evermaw region|Evermaw travel" \
  --path "Evermaw" --passages 10
```

Paginate with `--offset` and `--passage-offset` when a document has more passages than shown. Use `coverage` to track which sources have been fully read:
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py coverage "<topic>" --path "<folder>"
```

Use `--context` to auto-size output for your LLM's context window:
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py research "<topic>" --context 8k
```

Use `--llm` for structured JSON with headings and coverage metadata:
```
python3 /mnt/sandisk_usb/pdf_search/pdf_research.py research "<topic>" --llm
```

Keep searching until you have enough material — aim for at least 8–12 distinct sources if they exist, or exhaust what's available for narrow topics. Gather more passages than you need.

Track for each document you cite:
- filename and path
- doc id
- total_passages count returned by the API for that query

## Step 3: Write the HTML report

Generate a filename slug from the topic and scope: e.g. `locations_evermaw` or `traps_shadowdark` or `traps`.

Write a complete HTML file synthesizing ONLY what you found in the passages. Do not add information from your training data. If the passages don't cover something, omit it.

Use this HTML template:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <title>TITLE HERE</title>
  <style>
    body {
      font-family: sans-serif;
      font-size: 1.25rem;
      line-height: 1.6;
      max-width: 80ch;
      margin: 2rem auto;
      padding: 0 1rem;
      background: #000;
      color: #eee;
    }
    a { color: #fff; }
    a:visited { color: #ccc; }
    header {
      border-bottom: 2px solid #555;
      margin-bottom: 2rem;
      padding-bottom: 1rem;
    }
    header h1 { margin: 0 0 0.25rem 0; font-size: 2.2rem; }
    header p { margin: 0; color: #888; font-size: 0.9rem; }
    h2 { font-size: 1.6rem; margin-top: 2rem; border-bottom: 1px solid #333; padding-bottom: 0.25rem; }
    em { color: #aaa; }
    table { border-collapse: collapse; width: 100%; font-size: 0.85rem; margin-top: 1rem; }
    th, td { border: 1px solid #444; padding: 0.4rem 0.6rem; text-align: left; }
    th { background: #111; }
    ul { padding-left: 1.4rem; }
    li { margin-bottom: 0.4rem; }
    nav { margin-top: 2rem; font-size: 0.85rem; color: #888; }
  </style>
</head>
<body>
  <header>
    <h1>TITLE HERE</h1>
    <p>RPG PDF Research &bull; <a href="index.html">All Reports</a></p>
  </header>

  <!-- structure varies by output intent — see below -->

  <nav><a href="index.html">&larr; All Reports</a></nav>
</body>
</html>
```

**Structure by output intent:**

- **Listing** — use a brief intro, then `<h2>` sections per category or source, with `<ul>` or `<table>` entries. Each item or row should note the source inline. Aim for completeness over prose depth.
- **Explanation** — use thematic `<h2>` sections grouping related findings. Prose paragraphs, ~2,000 words. Don't summarize document by document.
- **Comparison** — use `<h2>` sections per dimension being compared, or a comparison table. Prose or table as fits.
- **Reference** — use `<h2>` sections per rule area or concept, with concise summaries and citations.

Citations: every paragraph or list section that draws on source material ends with one or more inline citations: (<em>Title</em>, YYYY) — infer a clean title from the filename, estimate year from context clues or folder path (e.g. "2e" → ~1995, "3e" → ~2001, "3.5" → ~2004, "5e" → ~2014–2024). Omit year if uncertain.

Sources table at the bottom: columns #, Title, File, Doc ID, Passages.

## Step 4: Save the report

Save the HTML file to: `/mnt/sandisk_usb/httpd/public_html/rpg_research/<slug>.html`

In the HTML file, the header subline should include a download link:
```html
<p>RPG PDF Research &bull; <a href="index.html">All Reports</a> &bull; <a href="<slug>.md" download>Download Markdown</a></p>
```

## Step 4b: Generate the Markdown version

Convert the HTML file to Markdown using pandoc:
```
pandoc /mnt/sandisk_usb/httpd/public_html/rpg_research/<slug>.html \
  --from html --to gfm --strip-comments \
  -o /mnt/sandisk_usb/httpd/public_html/rpg_research/<slug>.md
```

## Step 5: Update the index

Read `/mnt/sandisk_usb/httpd/public_html/rpg_research/index.html` and add a new `<li>` entry for this report inside the `<ul>`. Keep entries in alphabetical order by title. Include a markdown download link after the report title:

```html
<li><a href="<slug>.html">Report Title</a><a class="dl" href="<slug>.md" download>↓ md</a></li>
```

The index already has `.dl { font-size: 0.75rem; color: #888; margin-left: 0.5rem; }` in its stylesheet.

## Step 6: Confirm

Report the local URL: `http://192.168.86.44:8080/rpg_research/<slug>.html`
