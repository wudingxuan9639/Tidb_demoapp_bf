import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'node:path';
export default defineConfig({
    plugins: [vue()],
    server: {
        host: '127.0.0.1',
        port: 8517,
        strictPort: true,
    },
    build: {
        rollupOptions: {
            input: {
                b: resolve(__dirname, 'index.html'),
                c: resolve(__dirname, 'c.html'),
            },
        },
    },
});
