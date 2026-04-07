import json
import requests
import os
import argparse
import time
import sys
import re
import xml.etree.ElementTree as ET

def parse_structure_xml(xml_text):
    xml_match = re.search(r'<wiki_structure>.*?</wiki_structure>', xml_text, re.DOTALL)
    if not xml_match:
        if "<pages>" in xml_text and "<sections>" in xml_text:
            xml_text = f"<wiki_structure>{xml_text}</wiki_structure>"
        else:
            return None
    else:
        xml_text = xml_match.group(0)
    
    try:
        root = ET.fromstring(xml_text)
        structure = {
            'id': 'generated-wiki',
            'title': root.find('title').text if root.find('title') is not None else 'Project Wiki',
            'description': root.find('description').text if root.find('description') is not None else '',
            'pages': [],
            'sections': [],
            'rootSections': []
        }
        
        for sec_el in root.findall('.//section'):
            section = {
                'id': sec_el.get('id', 'sec-' + str(len(structure['sections']))),
                'title': sec_el.find('title').text if sec_el.find('title') is not None else 'Section',
                'pages': [p_ref.text for p_ref in sec_el.findall('.//page_ref')],
                'subsections': []
            }
            structure['sections'].append(section)
            structure['rootSections'].append(section['id'])
            
        for page_el in root.findall('.//page'):
            page = {
                'id': page_el.get('id', 'page-' + str(len(structure['pages']))),
                'title': page_el.find('title').text if page_el.find('title') is not None else 'Untitled Page',
                'description': page_el.find('description').text if page_el.find('description') is not None else '',
                'content': '',
                'filePaths': [f_path.text for f_path in page_el.findall('.//file_path')],
                'importance': page_el.find('importance').text if page_el.find('importance') is not None else 'medium',
                'relatedPages': []
            }
            structure['pages'].append(page)
        return structure
    except Exception as e:
        print(f"Failed to parse XML: {e}")
        return None

def load_structure_from_devin(repo_path):
    # Map repo_path to actual local path if needed
    # For gonzalo workspace, /apps/heycrypto maps to /home/gonzalo/workspace/auto_heycrypto
    actual_path = repo_path
    if repo_path == "/apps/heycrypto":
        actual_path = "/home/gonzalo/workspace/auto_heycrypto"
    
    devin_wiki_path = os.path.join(actual_path, ".devin", "wiki.json")
    if not os.path.exists(devin_wiki_path):
        return None
    
    print(f"Found .devin/wiki.json at {devin_wiki_path}. Using it for structure.")
    try:
        with open(devin_wiki_path, 'r') as f:
            devin_data = json.load(f)
        
        structure = {
            'id': 'devin-wiki',
            'title': 'Auto HeyCrypto Wiki',
            'description': 'System documentation driven by .devin configuration',
            'pages': [],
            'sections': [],
            'rootSections': []
        }
        
        # Create a default section
        main_section = {'id': 'main', 'title': 'Documentation', 'pages': [], 'subsections': []}
        
        for i, p in enumerate(devin_data.get('pages', [])):
            page_id = p['title'].lower().replace(" ", "-").replace("(", "").replace(")", "")
            page = {
                'id': page_id,
                'title': p['title'],
                'description': p.get('purpose', ''),
                'notes': " ".join([n['content'] for n in p.get('page_notes', [])]),
                'content': '',
                'filePaths': [], # We'll let AI find files based on title/notes
                'importance': 'high',
                'relatedPages': []
            }
            structure['pages'].append(page)
            main_section['pages'].append(page_id)
            
        structure['sections'].append(main_section)
        structure['rootSections'].append('main')
        return structure
    except Exception as e:
        print(f"Error loading .devin/wiki.json: {e}")
        return None

def batch_generate(repo_path, provider="ollama", model="gemma4:latest", language="en"):
    api_url = "http://localhost:8001"
    cache_dir = os.path.expanduser("~/.adalflow/wikicache")
    
    # New convention: deepwiki_cache_local_localpath_apps_heycrypto_en.json
    safe_repo_name = repo_path.strip("/").replace("/", "_")
    cache_filename = f"deepwiki_cache_local_localpath_{safe_repo_name}_{language}.json"
    cache_filepath = os.path.join(cache_dir, cache_filename)
    
    print(f"--- Starting Batch Wiki Generation ---")
    
    structure = None
    existing_generated_pages = {}
    
    if os.path.exists(cache_filepath):
        print(f"Found existing cache. Loading...")
        with open(cache_filepath, 'r') as f:
            cache_data = json.load(f)
            structure = cache_data.get('wiki_structure')
            existing_generated_pages = cache_data.get('generated_pages', {})
    else:
        # Migration from old 'none' format
        old_filename = f"deepwiki_cache_local_none_{safe_repo_name}_{language}.json"
        old_path = os.path.join(cache_dir, old_filename)
        if os.path.exists(old_path):
            print(f"Migrating old cache format to new...")
            os.rename(old_path, cache_filepath)
            with open(cache_filepath, 'r') as f:
                cache_data = json.load(f)
                structure = cache_data.get('wiki_structure')
                existing_generated_pages = cache_data.get('generated_pages', {})
    
    if not structure:
        # Try .devin first
        structure = load_structure_from_devin(repo_path)
        
        if not structure:
            print("No .devin/wiki.json found. Falling back to AI deep analysis...")
            struct_resp = requests.get(f"{api_url}/local_repo/structure?path={repo_path}")
            if struct_resp.status_code != 200:
                print(f"Error: {struct_resp.text}")
                return
            repo_data = struct_resp.json()
            detailed_prompt = f"Analyze this project and create a COMPREHENSIVE wiki structure XML. Path: {repo_path}\nTree:\n{repo_data['file_tree']}\nReadme:\n{repo_data['readme']}"
            resp = requests.post(f"{api_url}/chat/completions/stream", json={
                "repo_url": repo_path, "type": "local", "provider": provider, "model": model, "language": language,
                "messages": [{"role": "user", "content": detailed_prompt}]
            }, stream=True)
            full_xml = ""
            for chunk in resp.iter_content(chunk_size=None):
                if chunk: full_xml += chunk.decode('utf-8')
            structure = parse_structure_xml(full_xml)
        
        if not structure:
            print("Failed to establish wiki structure.")
            return
            
        print(f"Structure established: '{structure['title']}' with {len(structure['pages'])} pages.")
        
        # Save initial cache
        save_body = {
            'repo': {'owner': 'localpath', 'repo': safe_repo_name, 'type': 'local', 'localPath': repo_path, 'repoUrl': repo_path},
            'language': language, 'comprehensive': True, 'wiki_structure': structure,
            'generated_pages': {p['id']: {**p, 'content': ''} for p in structure['pages']},
            'provider': provider, 'model': model
        }
        requests.post(f"{api_url}/api/wiki_cache", json=save_body)

    pages = structure.get('pages', [])
    total = len(pages)
    
    for i, page in enumerate(pages):
        page_id = page['id']
        if page_id in existing_generated_pages and len(existing_generated_pages[page_id].get('content', '')) > 300:
            print(f"[{i+1}/{total}] Skipping '{page['title']}' (already cached)")
            continue
            
        print(f"[{i+1}/{total}] Generating: {page['title']}...")
        
        # Use notes if available from .devin
        notes_str = f"Specific Notes: {page.get('notes','')}" if page.get('notes') else ""
        prompt_content = f"""Generate a detailed technical wiki page in Markdown for: {page['title']}
Purpose: {page.get('description','')}
{notes_str}
Files to analyze: {', '.join(page.get('filePaths', [])) if page.get('filePaths') else 'Determine relevant files from the project structure.'}

Instructions:
1. Start with a <details><summary>Relevant source files</summary></details>
2. Use # {page['title']}
3. Use Mermaid diagrams.
"""

        try:
            start_time = time.time()
            response = requests.post(f"{api_url}/chat/completions/stream", json={
                'repo_url': repo_path, 'type': 'local', 'provider': provider, 'model': model, 'language': language,
                'messages': [{'role': 'user', 'content': prompt_content}]
            }, stream=True)
            
            if response.status_code == 200:
                content = ""
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        content += chunk.decode('utf-8')
                        sys.stdout.write("."); sys.stdout.flush()
                
                print(f" Done! ({int(time.time() - start_time)}s)")

                # Improved cleanup: Only strip outer markdown blocks if they wrap the entire content
                content_clean = content.strip()
                if content_clean.startswith('```markdown') and content_clean.endswith('```'):
                    # Strip the outer wrapper
                    content_clean = re.sub(r'^```markdown\s*', '', content_clean)
                    content_clean = re.sub(r'\s*```$', '', content_clean)
                elif content_clean.startswith('```') and content_clean.endswith('```') and not content_clean.startswith('```mermaid'):
                    # Handle cases where it's just ``` without the markdown hint
                    content_clean = re.sub(r'^```\s*', '', content_clean)
                    content_clean = re.sub(r'\s*```$', '', content_clean)

                page_copy = page.copy()
                page_copy['content'] = content_clean
                
                # Immediate Save/Merge
                save_body = {
                    'repo': {'owner': 'localpath', 'repo': safe_repo_name, 'type': 'local', 'localPath': repo_path, 'repoUrl': repo_path},
                    'language': language, 'comprehensive': True, 'wiki_structure': structure,
                    'generated_pages': {page_id: page_copy},
                    'provider': provider, 'model': model
                }
                requests.post(f"{api_url}/api/wiki_cache", json=save_body)
            else:
                print(f"Error: {response.status_code}")
        except Exception as e:
            print(f"Exception: {e}")
        time.sleep(2)

    print("--- Batch Generation Complete ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--model", default="gemma4:latest")
    args = parser.parse_args()
    batch_generate(args.path, model=args.model)
