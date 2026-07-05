import re
from bs4 import BeautifulSoup, NavigableString, Comment

class HTMLToMarkdownConverter:
    """
    Parses Zendesk HTML body content into clean, normalized GitHub-Flavored Markdown.
    """
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

        # Strip navigation, header, footer, ads, sidebar elements
        if tag_name in ['nav', 'header', 'footer', 'aside', 'script', 'style']:
            return ""
        
        # Check class and id for keywords to exclude non-essential sections
        classes = node.get('class', [])
        if isinstance(classes, str):
            classes = [classes]
        node_id = node.get('id', '').lower()
        exclude_keywords = [
            'navigation', 'nav-bar', 'sidebar', 'footer', 'header',
            'related-articles', 'feedback-section', 'social-share',
            'adsense', 'advertisement', 'promo-banner'
        ]
        
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

        # Bold formatting
        if tag_name in ['strong', 'b']:
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children)
            if not content.strip():
                return ""
            left_spaces = content[:len(content) - len(content.lstrip())]
            right_spaces = content[len(content.rstrip()):]
            return f"{left_spaces}**{content.strip()}**{right_spaces}"

        # Italic formatting
        elif tag_name in ['em', 'i']:
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children)
            if not content.strip():
                return ""
            left_spaces = content[:len(content) - len(content.lstrip())]
            right_spaces = content[len(content.rstrip()):]
            return f"{left_spaces}*{content.strip()}*{right_spaces}"

        # Code block / Inline code
        elif tag_name == 'code':
            parent_name = node.parent.name.lower() if node.parent and node.parent.name else ""
            if parent_name == 'pre':
                return node.get_text()
            else:
                return f"`{node.get_text()}`"

        # Code Blocks
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

        # Links
        elif tag_name == 'a':
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children).strip()
            href = node.get('href', '')
            if not href:
                return content
            if not content:
                content = node.get('title', href)
            return f"[{content}]({href})"

        # Images
        elif tag_name == 'img':
            alt = node.get('alt', '')
            src = node.get('src', '')
            return f"![{alt}]({src})"

        # Breaks & Horizontal Rules
        elif tag_name == 'br':
            return "\n"
        elif tag_name == 'hr':
            return "\n\n---\n\n"

        # Paragraphs & Blocks
        elif tag_name in ['p', 'div', 'blockquote']:
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children)
            if not content.strip():
                return ""
            if tag_name == 'blockquote':
                lines = content.strip().split('\n')
                formatted_lines = [f"> {line}" for line in lines]
                return f"\n\n" + "\n".join(formatted_lines) + "\n\n"
            return f"\n\n{content.strip()}\n\n"

        # Headings
        elif tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag_name[1])
            content = "".join(self._traverse(child, list_level, list_type) for child in node.children).strip()
            if not content:
                return ""
            prefix = "#" * level
            return f"\n\n{prefix} {content}\n\n"

        # Unordered Lists
        elif tag_name == 'ul':
            items = []
            for child in node.children:
                if child.name and child.name.lower() == 'li':
                    items.append(self._traverse(child, list_level + 1, 'ul'))
            content = "\n".join(items)
            return f"\n{content}\n"

        # Ordered Lists
        elif tag_name == 'ol':
            items = []
            idx = 1
            for child in node.children:
                if child.name and child.name.lower() == 'li':
                    items.append(self._traverse(child, list_level + 1, 'ol', idx))
                    idx += 1
            content = "\n".join(items)
            return f"\n{content}\n"

        # List Items
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

        # Tables
        elif tag_name == 'table':
            tr_elements = node.find_all('tr', recursive=True)
            if not tr_elements:
                return ""
            
            first_row = tr_elements[0]
            th_elements = first_row.find_all(['th', 'td'])
            has_headers = bool(node.find_all('th'))
            
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
    """
    Extracts a clean, safe filename slug from the Zendesk article.
    """
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
