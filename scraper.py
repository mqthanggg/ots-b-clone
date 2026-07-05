import ssl
import json
import urllib.request

def fetch_zendesk_articles(target_count=250):
    """
    Queries the public Zendesk Help Center API with pagination to scrape up to target_count articles.
    """
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
