import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  root: 'panel',
  server: {
    port: 5173,
    strictPort: true,
  },
});
