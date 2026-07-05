import os
import json
from google import genai

from converter import HTMLToMarkdownConverter, get_slug
from scraper import fetch_zendesk_articles
from chunker import chunk_markdown

# ==========================================
# 1. Zero-dependency Dotenv Loader
# ==========================================
def load_dotenv(dotenv_path=".env"):
    """
    Loads environment variables from a local .env file.
    """
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
# 2. Orchestration & Stateless Delta Sync
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
        
    # A. Fetch fresh Zendesk data (up to 250 articles)
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
    sync_state = {}
    for f in gemini_files:
        disp = f.display_name
        if disp and disp.startswith("optibot_"):
            parts = disp.split("_", 2)
            if len(parts) == 3:
                art_id = int(parts[1])
                timestamp = parts[2]
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
        updated_at = article.get('updated_at', '')
        
        slug = get_slug(article)
        filename = f"{slug}.md"
        filepath = os.path.join(articles_dir, filename)
        
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
