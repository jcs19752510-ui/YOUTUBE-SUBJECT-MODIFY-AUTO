import path from 'node:path';
const fe = path.resolve(__dirname, '../../frontend');
export default ({
  root: fe,
  esbuild: { jsx: 'automatic' },
  server: { fs: { allow: [path.resolve(__dirname, '../..')] } },
  test: { environment: 'jsdom', globals: true, setupFiles: [path.join(fe, 'src/test/setup.ts')], css: false,
    include: [path.resolve(__dirname, '*.test.tsx')] },
});
