#!/usr/bin/env bash
# Reuse the already-downloaded Qwen weights and vLLM image; never pull/download.
set -euo pipefail

FLOODWATCH_LLM_PORT="${FLOODWATCH_LLM_PORT:-8002}"
FLOODWATCH_LLM_CONTAINER="${FLOODWATCH_LLM_CONTAINER:-floodwatch-vllm}"
VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:qwen3_5-x86_64-cu130}"
LLM_MODEL="${LLM_MODEL:-qwen35}"
HF_MODEL_CACHE="${HF_MODEL_CACHE:-$HOME/models/huggingface}"
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-8192}"
VLLM_GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.35}"

command -v docker >/dev/null || { echo 'Docker is required for the existing vLLM image.' >&2; exit 1; }
command -v curl >/dev/null || { echo 'curl is required to check the model service.' >&2; exit 1; }

# An already-running matching endpoint takes precedence over launching another.
if curl --silent --fail --max-time 5 "http://127.0.0.1:$FLOODWATCH_LLM_PORT/v1/models" |
  python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(not any(m["id"] == sys.argv[1] for m in data.get("data",[])))' "$LLM_MODEL" 2>/dev/null; then
  echo "Reusing $LLM_MODEL at http://127.0.0.1:$FLOODWATCH_LLM_PORT/v1"
  exit 0
fi

docker image inspect "$VLLM_IMAGE" >/dev/null 2>&1 || {
  echo "Cached vLLM image is missing: $VLLM_IMAGE. No image was downloaded." >&2; exit 1;
}

if docker container inspect "$FLOODWATCH_LLM_CONTAINER" >/dev/null 2>&1; then
  owner=$(docker inspect --format '{{index .Config.Labels "floodwatch.service"}}' "$FLOODWATCH_LLM_CONTAINER")
  [[ "$owner" == 'llm' ]] || { echo 'Refusing to modify a container not owned by FloodWatch.' >&2; exit 1; }
  docker start "$FLOODWATCH_LLM_CONTAINER" >/dev/null
  echo "Started/reused $FLOODWATCH_LLM_CONTAINER with its existing configuration."
else
  HF_MODEL_CACHE=$(realpath "$HF_MODEL_CACHE")
  snapshot_root="$HF_MODEL_CACHE/hub/models--Qwen--Qwen3.5-4B"
  revision=$(cat "$snapshot_root/refs/main")
  [[ "$revision" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid cached Qwen snapshot revision.' >&2; exit 1; }
  model_path="$snapshot_root/snapshots/$revision"
  python3 - "$model_path" <<'PY'
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
config = json.loads((path / 'config.json').read_text())
assert 'Qwen3_5ForConditionalGeneration' in config['architectures'], 'Unexpected model architecture'
weights = json.loads((path / 'model.safetensors.index.json').read_text())['weight_map']
for name in set(weights.values()):
    assert (path / name).is_file(), f'Missing cached weight file: {name}'
assert (path / 'tokenizer.json').is_file(), 'Missing tokenizer'
print(f'Using complete local Qwen snapshot: {path}')
PY
  container_model="/models/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/$revision"
  docker run --detach --pull never \
    --name "$FLOODWATCH_LLM_CONTAINER" --label floodwatch.service=llm \
    --gpus 'device=0' --shm-size 2g --cpus 4 \
    --publish "127.0.0.1:$FLOODWATCH_LLM_PORT:8000" \
    --mount "type=bind,src=$HF_MODEL_CACHE,dst=/models/huggingface,readonly" \
    --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
    --env VLLM_NO_USAGE_STATS=1 --env DO_NOT_TRACK=1 \
    --env OMP_NUM_THREADS=4 --env MKL_NUM_THREADS=4 \
    --env LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/local/nvidia/lib64:/usr/local/nvidia/lib \
    "$VLLM_IMAGE" \
    --model "$container_model" --served-model-name "$LLM_MODEL" \
    --host 0.0.0.0 --port 8000 --max-model-len "$VLLM_MAX_MODEL_LEN" \
    --gpu-memory-utilization "$VLLM_GPU_MEMORY_UTILIZATION" \
    --max-num-seqs 2 --max-num-batched-tokens 8192 \
    --dtype auto --language-model-only --enforce-eager \
    --default-chat-template-kwargs '{"enable_thinking":false}' >/dev/null
  echo "Started $FLOODWATCH_LLM_CONTAINER. Initial loading can take a few minutes."
fi

echo "LLM_BASE_URL=http://127.0.0.1:$FLOODWATCH_LLM_PORT/v1"
echo "LLM_MODEL=$LLM_MODEL"
echo "Follow startup: docker logs -f $FLOODWATCH_LLM_CONTAINER"
echo "Readiness: curl --fail http://127.0.0.1:$FLOODWATCH_LLM_PORT/v1/models"
echo "Stop only this model service: docker stop $FLOODWATCH_LLM_CONTAINER"
