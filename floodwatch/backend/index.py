"""Atomic SQLite vector index. Run: python3 -m backend.index --rebuild."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from .config import Settings
from .vectors import embeddings, fit_tfidf, cosine

CHUNK_SIZE = 1100
CHUNK_OVERLAP = 180

class IndexUnavailable(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def documents(directory):
    root = directory.resolve()
    docs = []
    for path in sorted(directory.rglob('*')):
        if path.suffix.lower() not in ('.md', '.txt') or not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError('Knowledge document symlinks must remain inside KNOWLEDGE_DIR')
        raw = path.read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError('Split documents larger than 1 MB: ' + path.name)
        text = raw.decode('utf-8').strip()
        if not text:
            continue
        name = path.relative_to(directory).as_posix()
        title = next((line.lstrip('# ').strip() for line in text.splitlines() if line.startswith('# ')), path.name)
        docs.append({'id': digest(name.encode() + b'\0' + raw)[:16], 'name': name, 'title': title,
                     'sha256': digest(raw), 'text': text})
    return docs


def chunk_text(text):
    # Prefer paragraph/line boundaries; hard split long lines, with bounded overlap.
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            cut = text.rfind('\n', start + CHUNK_SIZE // 2, end)
            if cut > start:
                end = cut
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        if end == len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)


def signature(settings, docs):
    # Prevent retrieving obsolete threshold docs after the active analysis changes.
    source_paths = [settings.root/'public/observations/manifest.json',
                    settings.root/'shared/water_classes.json', settings.root/'scripts/analyze_water.py']
    manifest_path = source_paths[0]
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('analysis_url'):
            source_paths.append(settings.root/'public'/manifest['analysis_url'])
    sources = {str(p.relative_to(settings.root)): digest(p.read_bytes()) for p in source_paths if p.is_file()}
    return {'version': 1, 'provider': settings.embedding_provider, 'model': settings.embedding_model,
        'embedding_base_url': settings.embedding_base_url, 'encoder_sha256': digest((Path(__file__).parent/'vectors.py').read_bytes()), 'chunk_size': CHUNK_SIZE, 'overlap': CHUNK_OVERLAP,
        'documents': {doc['name']: doc['sha256'] for doc in docs}, 'project_sources': sources}


def rebuild(settings):
    docs = documents(settings.knowledge_dir)
    if not docs:
        raise ValueError('No Markdown or TXT documents found in KNOWLEDGE_DIR')
    chunks = [(doc, i, text) for doc in docs for i, text in enumerate(chunk_text(doc['text']))]
    expected_signature = signature(settings, docs)
    texts = [doc['title'] + '\n' + text for doc, _, text in chunks]
    idf = fit_tfidf(texts) if settings.embedding_provider == 'tfidf' else {}
    vectors = []
    for start in range(0, len(texts), 16):
        vectors.extend(embeddings(settings, texts[start:start+16], idf))
    if expected_signature != signature(settings, documents(settings.knowledge_dir)):
        raise ValueError('Sources changed while indexing; retry the rebuild')
    metadata = {'signature': expected_signature, 'idf': idf,
                'created_at': datetime.now(timezone.utc).isoformat(), 'chunk_count': len(chunks)}
    if settings.embedding_provider == 'openai':
        metadata['dimensions'] = len(vectors[0])
        if any(len(v) != metadata['dimensions'] for v in vectors):
            raise ValueError('Embedding dimensions changed during indexing')
    settings.index_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve immutable cited source versions across later index rebuilds.
    snapshots = settings.index_path.parent/'sources'
    snapshots.mkdir(exist_ok=True)
    for doc in docs:
        snapshot = snapshots/(doc['id'] + '.json')
        if not snapshot.exists():
            snapshot.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    fd, name = tempfile.mkstemp(dir=settings.index_path.parent, suffix='.sqlite3')
    os.close(fd)
    try:
        with sqlite3.connect(name) as db:
            db.executescript('CREATE TABLE metadata (value TEXT); CREATE TABLE documents (id TEXT PRIMARY KEY, name TEXT, title TEXT, sha256 TEXT, text TEXT); CREATE TABLE chunks (doc_id TEXT, ordinal INTEGER, text TEXT, vector TEXT);')
            db.execute('INSERT INTO metadata VALUES (?)', (json.dumps(metadata),))
            db.executemany('INSERT INTO documents VALUES (:id,:name,:title,:sha256,:text)', docs)
            db.executemany('INSERT INTO chunks VALUES (?,?,?,?)', [(doc['id'], i, text, json.dumps(vector)) for (doc,i,text),vector in zip(chunks,vectors)])
        os.replace(name, settings.index_path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return {'documents': len(docs), 'chunks': len(chunks), 'embedding_provider': settings.embedding_provider, 'embedding_model': settings.embedding_model}


class Index:
    def __init__(self, settings):
        self.settings = settings
        if not settings.index_path.is_file():
            raise IndexUnavailable('Knowledge index is missing. Run python3 -m backend.index --rebuild.')
        self.db = sqlite3.connect(f'file:{settings.index_path}?mode=ro', uri=True)
        self.db.row_factory = sqlite3.Row
        self.metadata = json.loads(self.db.execute('SELECT value FROM metadata').fetchone()[0])

    def __enter__(self): return self
    def __exit__(self, *_): self.db.close()

    def check_fresh(self):
        if self.metadata['signature'] != signature(self.settings, documents(self.settings.knowledge_dir)):
            raise IndexUnavailable('Knowledge or model settings changed. Run python3 -m backend.index --rebuild before chatting.')

    def retrieve(self, query):
        self.check_fresh()
        vector = embeddings(self.settings, [query], self.metadata['idf'])[0]
        if self.settings.embedding_provider == 'openai' and len(vector) != self.metadata['dimensions']:
            raise IndexUnavailable('Embedding model dimensions changed. Rebuild the index.')
        results = []
        for row in self.db.execute('SELECT c.*, d.title, d.name, d.sha256 FROM chunks c JOIN documents d ON c.doc_id=d.id'):
            score = cosine(vector, json.loads(row['vector']))
            # Lexical cutoff removes chance n-gram overlaps, not a probability of truth.
            if score >= (.015 if self.settings.embedding_provider == 'tfidf' else .25):
                results.append({**dict(row), 'score': score})
        results.sort(key=lambda row: row['score'], reverse=True)
        selected, doc_counts = [], {}
        for row in results:
            if doc_counts.get(row['doc_id'], 0) >= 2:
                continue
            row.pop('vector')
            selected.append(row)
            doc_counts[row['doc_id']] = doc_counts.get(row['doc_id'], 0) + 1
            if len(selected) == self.settings.top_k:
                break
        return selected

    def document(self, doc_id):
        row = self.db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
        if row:
            return dict(row)
        if re.fullmatch(r'[0-9a-f]{16}', doc_id):
            snapshot = self.settings.index_path.parent/'sources'/(doc_id + '.json')
            if snapshot.is_file():
                return json.loads(snapshot.read_text())
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild', action='store_true')
    parser.add_argument('--query')
    parser.add_argument('--no-refresh', action='store_true', help='Only for a custom knowledge directory; skip generated project docs')
    args = parser.parse_args()
    settings = Settings.load()
    if args.rebuild:
        if not args.no_refresh and settings.knowledge_dir == settings.root/'knowledge':
            subprocess.run([sys.executable, str(settings.root/'scripts/refresh_knowledge.py')], cwd=settings.root, check=True)
        print(json.dumps(rebuild(settings), ensure_ascii=False, indent=2))
    if args.query:
        with Index(settings) as index:
            print(json.dumps(index.retrieve(args.query), ensure_ascii=False, indent=2))
    if not args.rebuild and not args.query:
        parser.error('Use --rebuild or --query QUESTION')

if __name__ == '__main__': main()
