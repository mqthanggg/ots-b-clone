import os
import re
import urllib.request
import json
import ssl
from bs4 import BeautifulSoup, NavigableString, Comment

class HTMLToMarkdownConverter:
    def __init__(self):
        pass

    def convert(self, html_content):
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, 'html.parser')
        raw_md = self._traverse(soup)
        # Collapse multiple blank lines
        clean_md = re.sub(r'\n{3,}', '\n\n', raw_md)
        return clean_md.strip()

    def _traverse(self, node, list_level=0, list_type=None, list_index=1):
        if isinstance(node, Comment):
            return ""
        if isinstance(node, NavigableString):
            return str(node)

        tag_name = node.name.lower() if node.name else ""

        # Check for nav, ad, and widgets to strip them out
        if tag_name in ['nav', 'header', 'footer', 'aside']:
            return ""
        
        # Check class and id for keywords
        classes = node.get('class', [])
        if isinstance(classes, str):
            classes = [classes]
        node_id = node.get('id', '').lower()
        exclude_keywords = ['navigation', 'nav-bar', 'sidebar', 'footer', 'header', 'related-articles', 'feedback-section', 'social-share', 'adsense', 'advertisement', 'promo-banner']
        
        has_exclude = False
        for cls in classes:
            cls_lower = str(cls).lower()
            if any(keyword in cls_lower for keyword in exclude_keywords):
                has_exclude = True
                break
        if not has_exclude:
            if any(keyword in node_id for keyword in exclude_keywords):
                has_exclude = True
        
        if has_exclude:
            return ""

        # Inline formatting tags
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

        # Block level tags
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
            
            all_th = node.find_all('th')
            if all_th:
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
