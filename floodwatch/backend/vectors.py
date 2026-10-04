"""Explicit lexical embeddings by default; optional separate semantic embedding API."""
from collections import Counter
import json
import math
import re
import urllib.request


def http_json(url, payload=None, api_key='', timeout=90):
    headers = {'Accept': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def terms(text):
    normalized = re.sub(r'\b(?:the|a|an|is|are|was|were|how|what|which|when|where|why|do|does|can|you|of|to|in|for|and|it|this|that|many)\b', ' ', text.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    words = re.findall(r'[a-z0-9]+', normalized)
    # Character n-grams support short Chinese queries without a tokenizer download.
    return Counter(['w:' + w for w in words] + ['c:' + normalized[i:i+n]
        for n in (2, 3, 4) for i in range(max(0, len(normalized)-n+1))
        if not normalized[i:i+n].isspace()])


def fit_tfidf(texts):
    frequencies = Counter()
    for text in texts:
        frequencies.update(terms(text).keys())
    return {term: math.log((1 + len(texts)) / (1 + count)) + 1 for term, count in frequencies.items()}


def lexical_vector(text, idf):
    vector = {term: (1 + math.log(count)) * idf[term] for term, count in terms(text).items() if term in idf}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    return {key: value / norm for key, value in vector.items()} if norm else {}


def embeddings(settings, texts, idf=None):
    if settings.embedding_provider == 'tfidf':
        return [lexical_vector(text, idf or {}) for text in texts]
    response = http_json(settings.embedding_base_url.rstrip('/') + '/embeddings',
        {'model': settings.embedding_model, 'input': texts}, settings.embedding_api_key, settings.timeout_seconds)
    rows = sorted(response['data'], key=lambda row: row['index'])
    if [row['index'] for row in rows] != list(range(len(texts))):
        raise ValueError('Embedding service returned incomplete vectors')
    vectors = []
    for row in rows:
        values = row['embedding']
        if not values or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError('Embedding service returned invalid vectors')
        norm = math.sqrt(sum(v*v for v in values))
        if not norm:
            raise ValueError('Embedding service returned an empty vector')
        vectors.append({str(i): value / norm for i, value in enumerate(values)})
    if len({len(v) for v in vectors}) != 1:
        raise ValueError('Embedding dimensions are inconsistent')
    return vectors


def cosine(left, right):
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0) for key, value in left.items())
