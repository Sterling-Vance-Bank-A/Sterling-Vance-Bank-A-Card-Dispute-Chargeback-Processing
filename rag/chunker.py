import os, re
from typing import List, Dict

CORPUS_PATH = os.path.join(os.path.dirname(__file__), 'corpus', 'sterling_vance_policy.txt')

def load_corpus() -> str:
    with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
        return f.read()

def chunk_by_section(text: str, max_chunk_tokens: int = 300) -> List[Dict]:
    lines = text.split('\n')
    chunks = []
    current_section = "Unknown"
    current_text = []
    char_offset = 0
    
    for line in lines:
        if line.startswith('SECTION ') or re.match(r'^\d+\.\d+', line):
            if current_text:
                chunk_text = '\n'.join(current_text)
                reason_code_match = re.search(r'[Cc]ode\s+(\d{4})|\b(48\d{2})\b', chunk_text)
                reason_code = reason_code_match.group(1) or reason_code_match.group(2) if reason_code_match else None
                chunks.append({
                    'chunk_id': f"sec_{len(chunks)}",
                    'text': chunk_text,
                    'section': current_section,
                    'doc_type': 'policy',
                    'reason_code': reason_code,
                    'page_estimate': 1,
                    'char_offset': char_offset - len(chunk_text)
                })
                current_text = []
            current_section = line.strip()
        current_text.append(line)
        char_offset += len(line) + 1
        
    if current_text:
        chunk_text = '\n'.join(current_text)
        reason_code_match = re.search(r'[Cc]ode\s+(\d{4})|\b(48\d{2})\b', chunk_text)
        reason_code = reason_code_match.group(1) or reason_code_match.group(2) if reason_code_match else None
        chunks.append({
            'chunk_id': f"sec_{len(chunks)}",
            'text': chunk_text,
            'section': current_section,
            'doc_type': 'policy',
            'reason_code': reason_code,
            'page_estimate': 1,
            'char_offset': char_offset - len(chunk_text)
        })
    return chunks

def chunk_fixed_size(text: str, chunk_size: int = 400, overlap: int = 50) -> List[Dict]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        chunk_text = ' '.join(chunk_words)
        chunks.append({
            'chunk_id': f"fix_{len(chunks)}",
            'text': chunk_text,
            'section': 'fixed',
            'doc_type': 'policy',
            'reason_code': None,
            'page_estimate': 1,
            'char_offset': i
        })
    return chunks

def get_chunks(strategy: str = 'section') -> List[Dict]:
    text = load_corpus()
    if strategy == 'section':
        return chunk_by_section(text)
    return chunk_fixed_size(text)
