import json
import re
import os

filepath = os.path.expanduser('~/.adalflow/wikicache/deepwiki_cache_local_none_apps_heycrypto_en.json')
if not os.path.exists(filepath):
    print(f"File not found: {filepath}")
    exit(1)

with open(filepath, 'r') as f:
    cache = json.load(f)

fixed_count = 0
patterns = [r'(?m)^(graph TD.*)$', r'(?m)^(sequenceDiagram.*)$', r'(?m)^(classDiagram.*)$', r'(?m)^(flowchart TD.*)$']

for pid, page in cache['generated_pages'].items():
    content = page.get('content', '')
    if not content: continue
    
    new_content = content
    # Only try to fix if it DOES NOT have mermaid code blocks already
    if '```mermaid' not in new_content:
        for p in patterns:
            match = re.search(p, new_content)
            if match:
                start_idx = match.start()
                # Find end (first triple newline or something that looks like the start of another section)
                # For simplicity, let's look for double newline as block separator
                remaining = new_content[start_idx:]
                
                # Mermaid diagrams often have many lines with no empty lines
                # We'll look for the next line that starts with something like '##' or end of string
                end_match = re.search(r'\n\s*##', remaining)
                if end_match:
                    end_idx = start_idx + end_match.start()
                else:
                    end_idx = len(new_content)
                
                mermaid_block = new_content[start_idx:end_idx].strip()
                # Ensure we don't double wrap if we find multiple diagrams
                new_content = new_content[:start_idx] + '```mermaid\n' + mermaid_block + '\n```\n' + new_content[end_idx:]
                fixed_count += 1

    page['content'] = new_content

with open(filepath, 'w') as f:
    json.dump(cache, f, indent=2)

print(f'Successfully repaired {fixed_count} pages containing Mermaid diagrams.')
