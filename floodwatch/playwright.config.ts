import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

// Keep the server's optional Conda browser dependency local to Chromium.
const browserEnv = Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
);
const condaLib = process.env.CONDA_PREFIX && join(process.env.CONDA_PREFIX, 'lib');
if (condaLib && existsSync(join(condaLib, 'libasound.so.2'))) {
  browserEnv.LD_LIBRARY_PATH = [condaLib, browserEnv.LD_LIBRARY_PATH].filter(Boolean).join(':');
}

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: 'http://127.0.0.1:4173',
    viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: {
      args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
      env: browserEnv,
    },
  },
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
