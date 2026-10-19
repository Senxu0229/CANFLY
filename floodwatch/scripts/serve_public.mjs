#!/usr/bin/env node
// Serve only the production build; keep the API and model on loopback.
import http from 'node:http';
import { createReadStream } from 'node:fs';
import { realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = await realpath(fileURLToPath(new URL('../dist/', import.meta.url)));
const port = Number(process.env.FLOODWATCH_PUBLIC_PORT || 8001);
const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon', '.webp': 'image/webp', '.tif': 'image/tiff',
  '.tiff': 'image/tiff', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8',
};
const fail = (res, status, message) => {
  if (res.headersSent) return res.destroy();
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end(message);
};

const server = http.createServer(async (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if (pathname.startsWith('/api/')) {
      if (!['GET', 'HEAD', 'POST'].includes(req.method)) return fail(res, 405, 'Method not allowed');
      const headers = { ...req.headers, host: '127.0.0.1:8787', connection: 'close' };
      delete headers.upgrade;
      const upstream = http.request({ hostname: '127.0.0.1', port: 8787,
        path: req.url, method: req.method, headers }, reply => {
        res.writeHead(reply.statusCode, reply.headers);
        reply.on('error', () => res.destroy());
        reply.pipe(res);
      });
      upstream.setTimeout(95000, () => upstream.destroy(new Error('API timeout')));
      upstream.on('error', () => fail(res, 502, 'Assistant API unavailable'));
      req.on('aborted', () => upstream.destroy());
      res.on('close', () => { if (!res.writableEnded) upstream.destroy(); });
      req.pipe(upstream);
      return;
    }
    if (!['GET', 'HEAD'].includes(req.method)) return fail(res, 405, 'Method not allowed');
    if (pathname.includes('\0') || pathname.split('/').some(part => part.startsWith('.'))) {
      return fail(res, 404, 'Not found');
    }
    const filename = await realpath(path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname)));
    if (!filename.startsWith(root + path.sep)) return fail(res, 404, 'Not found');
    const info = await stat(filename);
    if (!info.isFile()) return fail(res, 404, 'Not found');
    res.writeHead(200, {
      'Content-Type': types[path.extname(filename)] || 'application/octet-stream',
      'Content-Length': info.size,
      'Cache-Control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
    });
    if (req.method === 'HEAD') return res.end();
    const stream = createReadStream(filename);
    stream.on('error', () => res.destroy());
    res.on('close', () => stream.destroy());
    stream.pipe(res);
  } catch (error) {
    fail(res, error instanceof URIError ? 400 : 404, 'Not found');
  }
});
server.listen(port, '127.0.0.1', () => console.log(`FloodWatch production server: http://127.0.0.1:${port}`));
