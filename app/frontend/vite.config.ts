import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  
  // Tauri dev server settings
  server: {
    port: 1420,
    strictPort: true,
    host: '127.0.0.1',  // localhost only
  },
  
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
  
  build: {
    // Produce a single output for Tauri to bundle
    outDir: 'dist',
    emptyOutDir: true,
    // No external chunks — everything bundled locally
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          ui: ['lucide-react', 'zustand'],
        },
      },
    },
  },
  
  // IMPORTANT: No CDN. All assets served locally.
  // Ensure no external URLs are injected.
  experimental: {},
})
