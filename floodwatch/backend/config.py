import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    knowledge_dir: Path = ROOT / 'knowledge'
    index_path: Path = ROOT / '.rag/index.sqlite3'
    llm_base_url: str = 'http://127.0.0.1:8002/v1'
    llm_model: str = 'qwen35'
    llm_api_key: str = ''
    embedding_provider: str = 'tfidf'
    embedding_model: str = 'char-ngram-tfidf-v1'
    embedding_base_url: str = ''
    embedding_api_key: str = ''
    top_k: int = 4
    timeout_seconds: int = 90

    @classmethod
    def load(cls):
        path = ROOT / 'chat.config.local.json'
        local = json.loads(path.read_text()) if path.exists() else {}
        values = {}
        for key, field in cls.__dataclass_fields__.items():
            if key == 'root':
                continue
            value = os.environ.get(key.upper(), local.get(key, field.default))
            if key in ('knowledge_dir', 'index_path'):
                value = Path(value).expanduser()
                if not value.is_absolute():
                    value = ROOT / value
            elif key in ('top_k', 'timeout_seconds'):
                value = int(value)
            values[key] = value
        settings = cls(**values)
        if not 1 <= settings.top_k <= 6 or not 5 <= settings.timeout_seconds <= 180:
            raise ValueError('Invalid retrieval or timeout settings')
        if settings.embedding_provider not in ('tfidf', 'openai'):
            raise ValueError('EMBEDDING_PROVIDER must be tfidf or openai')
        if settings.embedding_provider == 'tfidf' and settings.embedding_model != 'char-ngram-tfidf-v1':
            raise ValueError('The tfidf provider requires EMBEDDING_MODEL=char-ngram-tfidf-v1')
        if settings.embedding_provider == 'openai' and not settings.embedding_base_url:
            raise ValueError('Set EMBEDDING_BASE_URL for the embedding service')
        return settings
