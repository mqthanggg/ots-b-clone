import os
import urllib.request
import json
import ssl
from converter import HTMLToMarkdownConverter, get_slug

def fetch_articles(target_count=30):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    articles = []
    # Fetch en-us articles specifically
    url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=30"
    
    print("Starting article ingestion pipeline...")
    while url and len(articles) < target_count:
        print(f"Requesting API endpoint: {url}")
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        try:
            with urllib.request.urlopen(req, context=ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
                batch = data.get('articles', [])
                print(f"Retrieved {len(batch)} articles in this batch.")
                articles.extend(batch)
                
                # Check for next page
                url = data.get('next_page')
        except Exception as e:
            print(f"Failed to fetch from {url}. Error: {e}")
            break
            
    print(f"Total articles retrieved: {len(articles)}")
    return articles[:max(target_count, len(articles))]


def main():
    target_dir = os.path.join(os.getcwd(), 'articles')
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"Created output directory: {target_dir}")

    articles = fetch_articles(target_count=30)
    converter = HTMLToMarkdownConverter()

    success_count = 0
    for idx, article in enumerate(articles):
        title = article.get('title', 'Untitled')
        body_html = article.get('body', '')
        html_url = article.get('html_url', '')
        
        slug = get_slug(article)
        if not slug:
            slug = f"article-{article.get('id', idx)}"
            
        filename = f"{slug}.md"
        filepath = os.path.join(target_dir, filename)
        
        print(f"[{idx+1}/{len(articles)}] Converting '{title}' -> {filename}...")
        
        markdown_body = converter.convert(body_html)
        
        # Build clean self-contained markdown document
        md_document = f"# {title}\n\n"
        md_document += f"[Original Article]({html_url})\n\n"
        md_document += markdown_body
        md_document += "\n"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_document)
            success_count += 1
        except Exception as e:
            print(f"  Error writing to {filename}: {e}")

    print(f"\nIngestion & Normalization complete. Successfully wrote {success_count}/{len(articles)} articles.")

if __name__ == "__main__":
    main()
