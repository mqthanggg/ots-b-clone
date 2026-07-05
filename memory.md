# Workspace Memory: OptiSigns Support Ingestion & Normalization

This workspace is dedicated to proving the capability of ingesting messy web content (Zendesk Help Center articles) and normalizing it into clean, structured Markdown files.

## Project Context
- **Source:** [support.optisigns.com](https://support.optisigns.com)
- **API Endpoint:** `https://support.optisigns.com/api/v2/help_center/en-us/articles.json`
- **Goal:** Fetch at least 30 articles, convert them to clean Markdown, and save as `<slug>.md`.
- **Target Location:** `articles/` directory in the workspace root.

## Architecture & Technology Decisions
1. **Language:** Python 3.14.0
2. **Key Libraries:** `urllib.request` (standard library for HTTP requests) and `BeautifulSoup4` (`bs4`) for parsing HTML.
3. **Markdown Conversion Strategy:**
   - **Body Ingestion:** Use Zendesk Help Center API, which naturally returns only the article's core body HTML (excluding navigation header/footer/sidebar/ads).
   - **Parsing HTML to Markdown:** A direct walk of the HTML DOM tree using BeautifulSoup.
     - Headings (`h1`-`h6`) -> converted to matching Markdown headings (`#` to `######`).
     - Paragraphs (`p`) -> normalized to simple text blocks.
     - Lists (`ul`, `ol`, `li`) -> nested Markdown list bullet points and numbers.
     - Formatting (`strong`, `em`, `code`, `pre`) -> mapped to `**`, `*`, inline backticks, and code blocks.
     - Links (`a`) -> `[text](url)` syntax. Crucially, **relative links** (e.g. anchor links `#section`, path links `/hc/...`) are preserved exactly.
     - Images (`img`) -> converted to `![alt](src)`.
     - Tables (`table`, `tr`, `th`, `td`) -> converted to standard Markdown tables.
   - **Filenames:** Generated as lowercased, slugified versions of the article's title (e.g., `Using the Japan Earthquake App` becomes `using-the-japan-earthquake-app.md`), removing any numerical prefixes or special characters.

## Codebase Structure & File Workflows

### 1. Ingestion Pipeline: [ingest_articles.py](file:///c:/Users/ThangMap/Desktop/Repositories/optibot-clone/ingest_articles.py)
* **Purpose:** Initial helper script that connects to the public Zendesk API and extracts help documents locally.
* **Internal Logic:**
  * Connects to `support.optisigns.com` via `urllib.request` and fetches up to 30 default articles.
  * Normalizes the raw HTML body of each article using `HTMLToMarkdownConverter` (BeautifulSoup tree-walker).
  * Writes them as clean `.md` files to the `articles/` directory.

### 2. Stateless Sync Orchestrator: [main.py](file:///c:/Users/ThangMap/Desktop/Repositories/optibot-clone/main.py)
* **Purpose:** The core daily sync job script (and default Docker command) that fetches Zendesk data and updates the Gemini File storage database.
* **Internal Logic (Steps):**
  1. **Scrapes Articles:** Queries Zendesk Help Center API with pagination (`per_page=100`) to retrieve up to 250 articles, guaranteeing full YouTube/asset guide coverage.
  2. **Resolves Gemini Storage state:** Fetches currently active files on the Gemini File API via `client.files.list()`. It filters files matching the prefix `optibot_<id>_<updated_at>` to check which documents are currently live.
  3. **Identifies Delta Operations:**
     * **NEW:** If a scraped Zendesk article ID is not found in the Gemini list, the script converts the content to markdown, generates the section chunks (1,500-char max, 200-char overlap), packages them into a single file, and uploads it under the display name `optibot_<id>_<updated_at>`.
     * **UPDATE:** If the article exists but its `updated_at` timestamp has changed, the old file is deleted from Gemini via `client.files.delete()` and the new version is compiled and uploaded under the new timestamp display name.
     * **SKIP:** If the article ID and timestamp match, it skips processing.
     * **DELETE:** If a file exists in the active Gemini list but is no longer present in the fresh Zendesk scraped list, it is removed from Gemini storage.
  4. **Outputs configuration:** Saves the list of all currently active Gemini file paths to `gemini_config.json` for validation and query usage.

### 3. Interactive CLI Assistant: [test_gemini_assistant.py](file:///c:/Users/ThangMap/Desktop/Repositories/optibot-clone/test_gemini_assistant.py)
* **Purpose:** Client tool that lets users query the support assistant and retrieve answers with precise article and section citations.
* **Internal Logic (Steps):**
  1. Loads `gemini_config.json` to resolve the list of currently active uploaded files.
  2. Checks each file with the Gemini API (`client.files.get()`) to ensure they are `ACTIVE` and ready.
  3. Detects if command-line arguments were provided:
     * **Single Query Mode:** Joining CLI arguments (e.g. `python test_gemini_assistant.py "How do I pair a screen?"`), querying the model, and exiting.
     * **Interactive Loop Mode:** If no arguments are provided, it starts an interactive loop (`while True`) prompting `User Question > ` for continuous support chat.
  4. Prompt construction: Injects the active file objects directly into the contents list passed to `gemini-2.5-flash` along with RAG strict rules (citation enforcement, concise lists).

## Progress Log
- **2026-07-03:**
  - Initialized implementation plan and workspace memory.
  - Verified public Zendesk API access and article body layout.
  - Implemented HTML-to-Markdown custom parser in `ingest_articles.py`.
  - Ran ingestion script and successfully retrieved, parsed, and saved 30 articles under `articles/` directory as slug-based markdown files.
  - Verified structure of sample generated markdown files (relative links, markdown tables, headings, image formatting are preserved).
- **2026-07-04:**
  - Designed and implemented a **Stateless Delta Sync Engine** inside [main.py](file:///c:/Users/ThangMap/Desktop/Repositories/optibot-clone/main.py) which compares Zendesk help center timestamps with file metadata (`optibot_<id>_<timestamp>`) stored directly on the Google Gemini File API, eliminating the need for databases or persistent volumes in cloud deployments.
  - Paginated Zendesk API scraping to retrieve up to 250 articles, ensuring full coverage of YouTube apps and specialized assets.
  - Handled delta operations: uploads new/updated files, deletes stale files, and skips unchanged documents.
  - Implemented multi-file context integration in the QA verification script [test_gemini_assistant.py](file:///c:/Users/ThangMap/Desktop/Repositories/optibot-clone/test_gemini_assistant.py).
  - Containerized the sync job using [Dockerfile](file:///c:/Users/ThangMap/Desktop/Repositories/optibot-clone/Dockerfile) and [requirements.txt](file:///c:/Users/ThangMap/Desktop/Repositories/optibot-clone/requirements.txt) based on `python:3.12-slim`.
  - Built the Docker image `optibot-sync` and ran it 4 times:
    - **Run 1:** Bootstrap run (uploaded 100 new articles).
    - **Run 2:** Identified parsing bug where hyphens in timestamps were globally replaced.
    - **Run 3:** Fixed parsing logic in `main.py`, rebuilt, and migrated file display names to corrected colon-based timestamps.
    - **Run 4:** Successfully verified 100% skip logic for unchanged files (Total Scraped: 250, New: 0, Updated: 0, Skipped: 100).
  - Validated programmatic QA retrieval in Docker, successfully answering *"How do I add a YouTube video?"* with step-by-step instructions and citations pointing back to the uploaded knowledge base files.
  - Cleaned up the repository by deleting unused OpenAI files and uninstalling the `openai` SDK to save space.

