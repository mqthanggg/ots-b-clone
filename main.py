import os
import re
import ssl
import json
import glob
import time
import urllib.request
from bs4 import BeautifulSoup
from google import genai

# ==========================================
# 1. Zero-dependency Dotenv Loader
# ==========================================
def load_dotenv(dotenv_path=".env"):
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from {dotenv_path}...")
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        os.environ[key] = val

# ==========================================
# 2. HTML to Markdown Converter & Ingestion
# ==========================================
class HTMLToMarkdownConverter:
    def convert(self, html_content):
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, 'html.parser')
        raw_md = self._traverse(soup)
        clean_md = re.sub(r'\n{3,}', '\n\n', raw_md)
        return clean_md.strip()

    def _traverse(self, node, list_level=0, list_type=None, list_index=1):
        if not node:
            return ""
        if node.name is None:
            # Check if navigable string or comment
            if node.parent and node.parent.name in ['script', 'style']:
                return ""
            if type(node).__name__ == 'Comment':
                return ""
            return str(node)

        tag_name = node.name.lower()
        if tag_name in ['nav', 'header', 'footer', 'aside', 'script', 'style']:
            return ""
        
        # Strip feedback & social shares
        classes = node.get('class', [])
        if isinstance(classes, str):
            classes = [classes]
        node_id = node.get('id', '').lower()
        exclude_keywords = ['navigation', 'nav-bar', 'sidebar', 'footer', 'header', 'related-articles', 'feedback-section', 'social-share', 'adsense', 'advertisement']
        if any(any(keyword in str(cls).lower() for keyword in exclude_keywords) for cls in classes) or any(keyword in node_id for keyword in exclude_keywords):
            return ""

        if tag_name in ['strong', 'b']:
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children)
            if not content.strip():
                return ""
            left_spaces = content[:len(content) - len(content.lstrip())]
            right_spaces = content[len(content.rstrip()):]
            return f"{left_spaces}**{content.strip()}**{right_spaces}"

        elif tag_name in ['em', 'i']:
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children)
            if not content.strip():
                return ""
            left_spaces = content[:len(content) - len(content.lstrip())]
            right_spaces = content[len(content.rstrip()):]
            return f"{left_spaces}*{content.strip()}*{right_spaces}"

        elif tag_name == 'code':
            parent_name = node.parent.name.lower() if node.parent and node.parent.name else ""
            if parent_name == 'pre':
                return node.get_text()
            else:
                return f"`{node.get_text()}`"

        elif tag_name == 'pre':
            code_tag = node.find('code')
            code_content = code_tag.get_text() if code_tag else node.get_text()
            lang = ""
            if code_tag and code_tag.has_attr('class'):
                for cls in code_tag['class']:
                    if cls.startswith('language-'):
                        lang = cls.split('-')[1]
                        break
            return f"\n\n```{lang}\n{code_content.rstrip()}\n```\n\n"

        elif tag_name == 'a':
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children).strip()
            href = node.get('href', '')
            if not href:
                return content
            if not content:
                content = node.get('title', href)
            return f"[{content}]({href})"

        elif tag_name == 'img':
            alt = node.get('alt', '')
            src = node.get('src', '')
            return f"![{alt}]({src})"

        elif tag_name == 'br':
            return "\n"

        elif tag_name == 'hr':
            return "\n\n---\n\n"

        elif tag_name in ['p', 'div', 'blockquote']:
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children)
            if not content.strip():
                return ""
            if tag_name == 'blockquote':
                lines = content.strip().split('\n')
                formatted_lines = [f"> {line}" for line in lines]
                return f"\n\n" + "\n".join(formatted_lines) + "\n\n"
            return f"\n\n{content.strip()}\n\n"

        elif tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag_name[1])
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children).strip()
            if not content:
                return ""
            prefix = "#" * level
            return f"\n\n{prefix} {content}\n\n"

        elif tag_name == 'ul':
            items = []
            for child in node.children:
                if child.name and child.name.lower() == 'li':
                    items.append(self._traverse(child, list_level + 1, 'ul'))
            content = "\n".join(items)
            return f"\n{content}\n"

        elif tag_name == 'ol':
            items = []
            idx = 1
            for child in node.children:
                if child.name and child.name.lower() == 'li':
                    items.append(self._traverse(child, list_level + 1, 'ol', idx))
                    idx += 1
            content = "\n".join(items)
            return f"\n{content}\n"

        elif tag_name == 'li':
            indent = "  " * (list_level - 1)
            prefix = "* " if list_type == 'ul' else f"{list_index}. "
            parts = []
            for child in node.children:
                parts.append(self._traverse(child, list_level, list_type))
            li_text = "".join(parts).strip()
            lines = li_text.split('\n')
            formatted_lines = []
            for i, line in enumerate(lines):
                if i == 0:
                    formatted_lines.append(f"{indent}{prefix}{line}")
                else:
                    formatted_lines.append(f"{indent}  {line}" if line.strip() else "")
            return "\n".join(formatted_lines)

        elif tag_name == 'table':
            tr_elements = node.find_all('tr', recursive=True)
            if not tr_elements:
                return ""
            headers = []
            has_headers = False
            first_row = tr_elements[0]
            th_elements = first_row.find_all(['th', 'td'])
            if node.find_all('th'):
                has_headers = True
            header_cells = []
            for cell in th_elements:
                cell_text = "".join(self._traverse(c, list_level, list_type) for c in cell.children).strip()
                cell_text = cell_text.replace('\n', ' ').replace('|', '\\|')
                header_cells.append(cell_text)
            rows = []
            rows.append("| " + " | ".join(header_cells) + " |")
            rows.append("| " + " | ".join(["---"] * len(header_cells)) + " |")
            start_idx = 1 if (has_headers or len(tr_elements) > 1) else 0
            for tr in tr_elements[start_idx:]:
                cells = tr.find_all(['td', 'th'])
                if not cells:
                    continue
                cell_texts = []
                for i in range(len(header_cells)):
                    if i < len(cells):
                        c = cells[i]
                        cell_text = "".join(self._traverse(child, list_level, list_type) for child in c.children).strip()
                        cell_text = cell_text.replace('\n', ' ').replace('|', '\\|')
                        cell_texts.append(cell_text)
                    else:
                        cell_texts.append("")
                rows.append("| " + " | ".join(cell_texts) + " |")
            return "\n\n" + "\n".join(rows) + "\n\n"

        else:
            return "".join(self._traverse(child, list_level, list_type) for child in node.children)

def get_slug(article):
    html_url = article.get('html_url', '')
    title = article.get('title', '')
    slug = ""
    if html_url:
        parts = html_url.split('/articles/')
        if len(parts) > 1:
            article_part = parts[1]
            article_part = re.sub(r'^\d+-?', '', article_part)
            slug = article_part.strip()
    if not slug:
        slug = title
    slug = slug.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug

def fetch_zendesk_articles(target_count=250):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    articles = []
    url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100"
    
    print("Requesting articles from Zendesk Support API...")
    while url and len(articles) < target_count:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, context=ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
                batch = data.get('articles', [])
                articles.extend(batch)
                url = data.get('next_page')
                print(f"  Retrieved {len(batch)} articles (Total: {len(articles)})")
        except Exception as e:
            print(f"  [ERROR] Failed to fetch from {url}: {e}")
            break
    return articles[:target_count]

# ==========================================
# 3. Markdown-Aware Section Chunker
# ==========================================
def chunk_markdown(content, title):
    lines = content.split('\n')
    sections = []
    current_header = "Introduction"
    current_lines = []
    
    for line in lines:
        header_match = re.match(r'^(#{1,4})\s+(.+)$', line)
        if header_match:
            if current_lines:
                sections.append((current_header, '\n'.join(current_lines)))
                current_lines = []
            current_header = header_match.group(2).strip()
        else:
            current_lines.append(line)
            
    if current_lines or not sections:
        sections.append((current_header, '\n'.join(current_lines)))
        
    chunks = []
    max_chars = 1500
    
    for header, text in sections:
        text = text.strip()
        if not text:
            continue
            
        metadata_prefix = f"Document: {title}\nSection: {header}\n---\n"
        prefix_len = len(metadata_prefix)
        available_len = max_chars - prefix_len
        
        if len(text) <= available_len:
            chunks.append(metadata_prefix + text)
        else:
            paragraphs = text.split('\n\n')
            sub_chunks = []
            current_sub_chunk = []
            current_len = 0
            
            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue
                
                if len(p) > available_len:
                    if current_sub_chunk:
                        sub_chunks.append('\n\n'.join(current_sub_chunk))
                        current_sub_chunk = []
                        current_len = 0
                    
                    sentences = re.split(r'(?<=[.!?])\s+', p)
                    sub_p_chunk = []
                    sub_p_len = 0
                    for s in sentences:
                        if sub_p_len + len(s) + 1 > available_len:
                            if sub_p_chunk:
                                sub_chunks.append(' '.join(sub_p_chunk))
                            sub_p_chunk = [s]
                            sub_p_len = len(s)
                        else:
                            sub_p_chunk.append(s)
                            sub_p_len += len(s) + 1
                    if sub_p_chunk:
                        sub_chunks.append(' '.join(sub_p_chunk))
                else:
                    if current_len + len(p) + 2 > available_len:
                        sub_chunks.append('\n\n'.join(current_sub_chunk))
                        last_p = current_sub_chunk[-1] if current_sub_chunk else ""
                        if last_p and len(last_p) + len(p) + 2 <= available_len:
                            current_sub_chunk = [last_p, p]
                            current_len = len(last_p) + len(p) + 2
                        else:
                            current_sub_chunk = [p]
                            current_len = len(p)
                    else:
                        current_sub_chunk.append(p)
                        current_len += len(p) + 2
            
            if current_sub_chunk:
                sub_chunks.append('\n\n'.join(current_sub_chunk))
                
            for s_idx, sub_text in enumerate(sub_chunks):
                part_info = f" [Part {s_idx+1}/{len(sub_chunks)}]" if len(sub_chunks) > 1 else ""
                meta_prefix = f"Document: {title}\nSection: {header}{part_info}\n---\n"
                chunks.append(meta_prefix + sub_text)
                
    return chunks

# ==========================================
# 4. Orchestration & Stateless Delta Sync
# ==========================================
def main():
    load_dotenv()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n[ERROR] GEMINI_API_KEY is not set.")
        print("Please check your .env configuration.")
        return
        
    client = genai.Client(api_key=api_key)
    
    articles_dir = os.path.join(os.getcwd(), 'articles')
    chunks_dir = os.path.join(os.getcwd(), 'chunks')
    
    if not os.path.exists(articles_dir):
        os.makedirs(articles_dir)
    if not os.path.exists(chunks_dir):
        os.makedirs(chunks_dir)
        
    # A. Fetch fresh Zendesk data
    scraped_articles = fetch_zendesk_articles(target_count=250)
    if not scraped_articles:
        print("[ERROR] No articles scraped from Zendesk Support.")
        return
        
    # B. Retrieve alive files on Gemini Storage
    print("\nRetrieving active files list from Gemini Storage...")
    gemini_files = []
    try:
        files_list = client.files.list()
        for f in files_list:
            gemini_files.append(f)
        print(f"  Found {len(gemini_files)} total active files in Gemini storage.")
    except Exception as e:
        print(f"[ERROR] Failed to list files on Gemini: {e}")
        return
        
    # Build sync state mapping: article_id -> (file_name, timestamp, display_name)
    # Convention for display_name: optibot_<article_id>_<timestamp_with_hyphens>
    sync_state = {}
    for f in gemini_files:
        disp = f.display_name
        if disp and disp.startswith("optibot_"):
            parts = disp.split("_", 2)
            if len(parts) == 3:
                art_id = int(parts[1])
                timestamp = parts[2]  # Reconstruct original ISO timestamp
                sync_state[art_id] = {
                    "file_name": f.name,
                    "updated_at": timestamp,
                    "display_name": disp
                }
                
    print(f"  Recognized {len(sync_state)} OptiSigns database files.")
    
    converter = HTMLToMarkdownConverter()
    
    new_uploads = 0
    updated_uploads = 0
    skipped_count = 0
    deleted_count = 0
    
    active_gemini_file_names = []
    
    # C. Match and Upload Deltas
    print("\nDetecting deltas and updating Gemini Knowledge Base...")
    
    scraped_ids = set()
    
    for article in scraped_articles:
        art_id = article.get('id')
        scraped_ids.add(art_id)
        
        title = article.get('title', 'Untitled')
        body_html = article.get('body', '')
        html_url = article.get('html_url', '')
        updated_at = article.get('updated_at', '')  # e.g., '2026-07-04T12:00:00Z'
        
        slug = get_slug(article)
        filename = f"{slug}.md"
        filepath = os.path.join(articles_dir, filename)
        
        # Keep the original timestamp intact in display_name
        display_name = f"optibot_{art_id}_{updated_at}"
        
        # Build Markdown content
        markdown_body = converter.convert(body_html)
        md_document = f"# {title}\n\n[Original Article]({html_url})\n\n{markdown_body}\n"
        
        # Save local copy
        with open(filepath, 'w', encoding='utf-8') as lf:
            lf.write(md_document)
            
        # Parse into chunks
        chunks = chunk_markdown(md_document, title)
        
        # Save chunks locally
        for idx, chunk_content in enumerate(chunks):
            chunk_filename = f"{slug}_chunk_{idx:03d}.md"
            chunk_filepath = os.path.join(chunks_dir, chunk_filename)
            with open(chunk_filepath, 'w', encoding='utf-8') as cf:
                cf.write(chunk_content)
                
        # Check delta
        if art_id not in sync_state:
            # Case 1: NEW Article
            print(f"  [NEW] Article: '{title}' (ID: {art_id}) - Uploading chunks...")
            
            # Combine the chunks for this article into a single article-knowledge-base file
            article_kb_path = os.path.join(chunks_dir, f"{slug}_kb_combined.md")
            with open(article_kb_path, 'w', encoding='utf-8') as akbf:
                for chunk in chunks:
                    akbf.write("================================================================================\n")
                    akbf.write(chunk)
                    akbf.write("\n================================================================================\n\n")
                    
            try:
                uploaded = client.files.upload(
                    file=article_kb_path,
                    config={'display_name': display_name}
                )
                active_gemini_file_names.append(uploaded.name)
                new_uploads += 1
                print(f"    Uploaded as {uploaded.name}")
            except Exception as e:
                print(f"    [ERROR] Failed upload: {e}")
            finally:
                if os.path.exists(article_kb_path):
                    os.remove(article_kb_path)
                    
        else:
            # Case 2: Article exists. Check if updated
            existing_record = sync_state[art_id]
            if existing_record["updated_at"] != updated_at:
                # UPDATED Article
                print(f"  [UPDATE] Article: '{title}' (ID: {art_id}) changed (Zendesk: {updated_at} vs Sync: {existing_record['updated_at']})...")
                print(f"    Deleting old file {existing_record['file_name']}...")
                try:
                    client.files.delete(name=existing_record['file_name'])
                except Exception as e:
                    print(f"    [WARNING] Failed to delete old file: {e}")
                    
                # Upload updated content
                article_kb_path = os.path.join(chunks_dir, f"{slug}_kb_combined.md")
                with open(article_kb_path, 'w', encoding='utf-8') as akbf:
                    for chunk in chunks:
                        akbf.write("================================================================================\n")
                        akbf.write(chunk)
                        akbf.write("\n================================================================================\n\n")
                        
                try:
                    uploaded = client.files.upload(
                        file=article_kb_path,
                        config={'display_name': display_name}
                    )
                    active_gemini_file_names.append(uploaded.name)
                    updated_uploads += 1
                    print(f"    Uploaded as {uploaded.name}")
                except Exception as e:
                    print(f"    [ERROR] Failed upload: {e}")
                finally:
                    if os.path.exists(article_kb_path):
                        os.remove(article_kb_path)
            else:
                # Case 3: UNCHANGED
                skipped_count += 1
                active_gemini_file_names.append(existing_record["file_name"])
                
    # D. Detect Deletions
    # If it is in sync_state but NOT in scraped_ids, it was deleted in Zendesk
    print("\nDetecting deletions...")
    for old_id, record in sync_state.items():
        if old_id not in scraped_ids:
            print(f"  [DELETE] Article ID {old_id} was deleted in Zendesk. Removing from Gemini Storage...")
            try:
                client.files.delete(name=record["file_name"])
                deleted_count += 1
                print(f"    Deleted file {record['file_name']} (display name: {record['display_name']})")
            except Exception as e:
                print(f"    [ERROR] Failed to delete: {e}")
                
    # E. Save configuration for verification script
    config_data = {
        "uploaded_files": active_gemini_file_names
    }
    config_path = os.path.join(os.getcwd(), 'gemini_config.json')
    with open(config_path, 'w', encoding='utf-8') as jf:
        json.dump(config_data, jf, indent=2)
        
    # Print summary
    print("\n" + "=" * 50)
    print("Daily Scraper-Uploader Sync Job Complete:")
    print(f"  - Total Scraped Zendesk Articles: {len(scraped_articles)}")
    print(f"  - New Articles Uploaded:          {new_uploads}")
    print(f"  - Updated Articles Re-uploaded:   {updated_uploads}")
    print(f"  - Unchanged Articles (Skipped):   {skipped_count}")
    print(f"  - Deleted Articles Removed:       {deleted_count}")
    print(f"  - Total Active Files in Storage:  {len(active_gemini_file_names)}")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    main()
