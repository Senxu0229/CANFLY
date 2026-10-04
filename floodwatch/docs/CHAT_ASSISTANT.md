# Local RAG map assistant

The existing React/Vite app now opens **Ask AI** as a chat panel at the lower right.
The project previously had no GIS API server. A small Python standard-library API
adds `/api/chat`, `/api/health`, `/api/context` and immutable local document citations.
Vite forwards `/api` to `127.0.0.1:8787` in both development and preview. Browser
clients need only the existing forwarded **5173** port. No API keys enter the browser.

## Start on this laboratory server

From `/home/grad/zqin/projects/hackathon/CANFLY/floodwatch`:

```bash
# Reuse the cached vLLM image and downloaded model. Starts a background container.
bash scripts/start_llm.sh

# Refresh the verified project documents and rebuild the vector index.
python3 -m backend.index --rebuild

# Run the local API in this terminal (Python 3.12; no pip dependencies).
python3 -m backend.server --port 8787
```

In another terminal, run the existing frontend if it is not already running:

```bash
source /home/grad/zqin/miniforge3/etc/profile.d/conda.sh
conda activate floodwatch-dev
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Refresh the browser and click **Ask AI**. The interface, questions and answers are in English.
Expanded evidence shows the original document text. Examples:

- `How is possible new water detected, and how large is it?`
- `What are the exact coordinates of this village?`
- `Which satellite acquired these images?`
- `Does orange mean the flood destroyed farmland?`

Changing the selected dates starts a fresh conversation and cancels the old
browser request. A request already being generated may finish on the server;
if an immediate retry says busy, wait briefly. Chat transcripts are held only in
the browser's memory and sent for the current request; the API does not save them.
The panel is a text assistant: it does not run GIS operations or inspect image pixels.

## Model configuration

Copy `chat.config.example.json` to **`chat.config.local.json`** to override defaults;
the latter is ignored by Git. Matching uppercase environment variables override
JSON settings. Generation and embedding configuration are independent.

| Setting | Current default |
| --- | --- |
| `LLM_BASE_URL` | `http://127.0.0.1:8002/v1` |
| `LLM_MODEL` | `qwen35` (served name of Qwen3.5-4B) |
| `LLM_API_KEY` | Empty for the local service |
| `EMBEDDING_PROVIDER` | `tfidf` |
| `EMBEDDING_MODEL` | `char-ngram-tfidf-v1` |
| `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` | Empty with TF-IDF |
| `KNOWLEDGE_DIR` | `knowledge` |
| `INDEX_PATH` | `.rag/index.sqlite3` |
| `TOP_K` | 4 passages |
| `TIMEOUT_SECONDS` | 90 |

The existing downloaded model is:

```text
/home/grad/zqin/models/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
```

The host's `/models/huggingface` directory does not exist; that path is used
inside the container. The startup script finds the local cache's current snapshot
and verifies its config, tokenizer and weight shards. The cached image is
`vllm/vllm-openai:qwen3_5-x86_64-cu130`. Its new `floodwatch-vllm` container leaves
other projects' stopped containers and the existing Ollama service untouched.
An already-running matching endpoint is reused. There are **no model/image downloads**:
image pulling is disabled, Hugging Face is offline, and model files are mounted read-only.

Current serving settings: GPU 0, 8192-token context, 35% GPU memory budget,
maximum two sequences, text-only, thinking disabled. Measured total VRAM allocation
is about 19.3 GiB including runtime overhead. First generation can need a longer
kernel warm-up; later tested requests took roughly 1–6 seconds. Context overflow
triggers one retry that trims history and retrieved passages while preserving the
mandatory rules, current map and question. If still too long, the API returns a
clear error instead of an invented answer.

```bash
curl http://127.0.0.1:8787/api/health
docker logs -f floodwatch-vllm
docker stop floodwatch-vllm
```

`/api/health` checks the index and model listing; a successful real chat is the
end-to-end readiness check. Configuration changes require restarting the Python
API. Existing containers keep their creation settings; use a distinct
`FLOODWATCH_LLM_CONTAINER` and free `FLOODWATCH_LLM_PORT` for a differently configured
service, then set `LLM_BASE_URL` accordingly.

### Embeddings and retrieval

No separate neural embedding weights were found locally. This first version
therefore fits **TF-IDF character/word vectors** over the small English corpus.
These are lexical embeddings, **not a downloaded semantic embedding model**.
They support reproducible cosine retrieval with no extra dependencies/downloads,
but paraphrases and cross-language matching are weaker than a multilingual neural
encoder. The generated documents include natural question variants.
Retrieval scores are ranking scores, not evidence confidence or model accuracy.

To use an independently available OpenAI-compatible semantic embedding service,
set `embedding_provider` to `openai`, and set its own `embedding_base_url`,
`embedding_model`, and optional `embedding_api_key`. This calls that service's
`/embeddings` endpoint, never the generation model automatically. Rebuild the index
and restart the API after changing these settings or the embedding weights. The
external-provider integration has unit tests with mocked responses; no external
embedding service was required or downloaded for this demo.

## Knowledge updates and source provenance

The six generated documents in `knowledge/generated/` cover:
location/dates, verified RADARSAT-2 product metadata, calibrated water-candidate
classification, colour meanings, active two-date statistics, and missing evidence.
They cite local filenames/paths and SHA256 hashes, including the active exported
manifest/report, actual classification script, shared class contract,
`kalari_abdu_analysis/calibration_info.json`, and four source `product.xml` files
under `/home/grad/zqin/datasets/hackathon`. Archived thresholds and mock datasets
are not indexed. There are no invented external references.

Add UTF-8 `.md` or `.txt` files in **`knowledge/custom/`** (subdirectories are
supported). Give each document a descriptive first Markdown heading, dated facts
and verifiable source references. Do not edit generated files by hand: refresh
regenerates them. Then run:

```bash
python3 -m backend.index --rebuild
# Equivalent package command: npm run rag:index

# Optional checks and direct retrieval inspection:
python3 scripts/refresh_knowledge.py --check
python3 -m backend.index --query 'How is possible new water detected?'
```

`--rebuild` refreshes generated docs, chunks Markdown/TXT (1100 characters with
180-character overlap), embeds them, and atomically publishes SQLite metadata,
source text and vectors. Source snapshots are content-versioned; existing cited
links retain their original text after a rebuild. The next request loads the new
index without an API restart. Added, edited or deleted documents, changes to the
active report/classifier, and changed embedding settings invalidate the index;
the API asks for a rebuild instead of silently using stale facts. A missing index
also fails clearly. A custom `KNOWLEDGE_DIR` can be indexed with `--no-refresh`.
The prototype is intended for a small collection of text documents, not raster,
PDF or image ingestion. Individual documents are limited to 1 MB.

## Grounding and interpretation rules

`shared/water_classes.json` supplies class IDs/meanings to the Python classifier,
PNG exporter, map legend and the assistant on **every request**:

- **Light blue:** possible new water, not confirmed inundation.
- **Dark blue:** possible water on both dates, not proven permanent water.
- **Orange:** brighter returns / departure from the earlier candidate mask;
  cause requires checking, not confirmed recession or crop damage.

The API accepts selected date IDs and view mode, and reconstructs statistics from
server-side exports. It rejects client-supplied statistics. Only the ordered pair
**2024-08-28 → 2024-09-21** has quantitative change analysis. Other pairs, including
the reverse order, carry an explicit no-statistics context. The current shared
threshold remains **−12.40234375 dB**; the chatbot does not change it.

The system prompt separates these mandatory rules and current-map facts from
retrieved documents/history, which are untrusted evidence and cannot override
rules. Replies must separate observations from hypotheses, state missing evidence,
and cite `[MAP]` or retrieved `[S1]` identifiers. Source cards link to real local
text or current-map JSON; excerpts can be expanded. Unknown citations, generated
URLs and incomplete/uncited answers fail validation. Only plain text is rendered.
These controls and tested examples reduce hallucinations; they do not constitute
independent validation of either the SAR classes or every future generated claim.

## Validation

```bash
python3 -m unittest discover -s backend -t . -p 'test_*.py'
npm run build
npm run test:e2e
```

Backend tests cover indexing/persistence, retrieval, stale source/model
rejection, source identity, date/area isolation, mandatory rules, prompt injection
placement, and citation validation. Browser tests cover chat context, sources,
errors/retries, cancellation, date changes, and mobile layout. Real Qwen requests
also verify coordinates, detection/statistics, the orange class, missing pair
statistics, and unavailable depth/casualty evidence. An isolated temporary corpus
was used to verify resistance to a retrieved instruction asking for invented crop
damage, a fake citation and an external URL; the active knowledge base was untouched.

The API and model bind only to loopback for this local Hackathon setup. A purely
static deployment needs the API proxy/server too; publishing `dist/` alone cannot
run a local model.
