import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base: './' keeps the build working from any folder (S3, GitHub Pages, a USB stick).
export default defineConfig({
  plugins: [react()],
  base: './',
});
