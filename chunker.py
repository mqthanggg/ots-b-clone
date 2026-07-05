import re

def chunk_markdown(content, title):
    """
    Splits markdown documents on heading boundaries, injecting document/heading context
    headers, and ensuring paragraph-based split control with character limits & overlap.
    """
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
