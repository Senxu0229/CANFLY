"""Local API (stdlib only). python3 -m backend.server --port 8787"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import re
import threading
from urllib.parse import parse_qs, urlsplit
from urllib.error import URLError
from .config import Settings
from .chat import respond, ModelResponseError
from .context import map_context
from .index import Index, IndexUnavailable
from .vectors import http_json

LOG = logging.getLogger('floodwatch.chat')


def handler(settings):
    gate = threading.BoundedSemaphore(1)
    class Handler(BaseHTTPRequestHandler):
        server_version = 'FloodWatchLocalAPI/1.0'

        def send(self, status, value, content_type='application/json; charset=utf-8'):
            data = json.dumps(value, ensure_ascii=False).encode() if content_type.startswith('application/json') else value.encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Client cancelled; never persist messages.

        def do_GET(self):
            path = urlsplit(self.path)
            try:
                if path.path == '/api/health':
                    info = {'status':'ready', 'llm_model':settings.llm_model,
                        'embedding_provider':settings.embedding_provider, 'embedding_model':settings.embedding_model}
                    try:
                        with Index(settings) as index:
                            index.check_fresh()
                            info['index_chunks'] = index.metadata['chunk_count']
                    except (ValueError, OSError) as error:
                        info.update(status='degraded', index_error=str(error))
                    try:
                        models = http_json(settings.llm_base_url.rstrip('/') + '/models', api_key=settings.llm_api_key, timeout=3)
                        info['model_service_ready'] = any(m['id']==settings.llm_model for m in models['data'])
                    except Exception:
                        info['model_service_ready'] = False
                    if not info['model_service_ready']: info['status'] = 'degraded'
                    return self.send(200, info)
                if path.path == '/api/context':
                    params = parse_qs(path.query)
                    value = map_context(settings, params.get('left_id',[''])[0], params.get('right_id',[''])[0], params.get('view_mode',['compare'])[0])
                    return self.send(200, value)
                match = re.fullmatch(r'/api/sources/([0-9a-f]{16})', path.path)
                if match:
                    with Index(settings) as index:
                        doc = index.document(match[1])
                    if doc:
                        return self.send(200, doc['text'], 'text/plain; charset=utf-8')
                    return self.send(404, {'error':'This source version is unavailable; rebuild or restart the conversation.'})
                return self.send(404, {'error':'Unknown API route'})
            except ValueError as error:
                return self.send(400, {'error':str(error)})
            except Exception:
                LOG.exception('API read failed')
                return self.send(503, {'error':'Local project data is unavailable. Check the server logs.'})

        def do_POST(self):
            if self.path != '/api/chat': return self.send(404, {'error':'Unknown API route'})
            # Only JSON same-origin requests through Vite. No permissive CORS/preflight.
            if self.headers.get_content_type() != 'application/json': return self.send(415, {'error':'Send application/json'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.send(400, {'error':'Invalid request length'})
            if not 0 < length <= 48000: return self.send(413, {'error':'Message payload is too large'})
            if not gate.acquire(blocking=False): return self.send(429, {'error':'The local assistant is busy. Please retry shortly.'})
            try:
                payload = json.loads(self.rfile.read(length))
                return self.send(200, respond(settings, payload))
            except IndexUnavailable as error:
                return self.send(503, {'error':str(error)})
            except ModelResponseError as error:
                return self.send(502, {'error':str(error)})
            except (URLError, TimeoutError, ConnectionError):
                return self.send(503, {'error':'The local model or embedding service is unavailable or timed out. Check the service and retry.'})
            except (ValueError, TypeError) as error:
                return self.send(400, {'error':str(error)})
            except Exception:
                LOG.exception('Chat request failed')
                return self.send(500, {'error':'Chat failed. Check the local server logs; no answer was fabricated.'})
            finally:
                gate.release()

        def log_message(self, fmt, *args):
            LOG.info('%s - %s', self.address_string(), fmt % args)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(Settings.load()))
    LOG.info('Local API listening on http://127.0.0.1:%s (no chat transcripts are saved)', args.port)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == '__main__': main()
