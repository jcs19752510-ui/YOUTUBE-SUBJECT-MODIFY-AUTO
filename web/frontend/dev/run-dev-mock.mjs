// 모의 서버와 Vite 개발 서버를 한 번에 띄운다. 종료(Ctrl+C) 시 둘 다 닫는다.
import { fileURLToPath } from 'node:url';
import { createServer as createVite } from 'vite';
import { startMockServer } from './mock-server.mjs';

const port = Number(process.env.MOCK_PORT ?? 8081);
const mock = await startMockServer({ port });
process.env.VITE_API_PROXY = `http://${mock.host}:${mock.port}`;
const vite = await createVite({
  configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
});
await vite.listen();
vite.printUrls();
console.log(
  `모의 API: ${process.env.VITE_API_PROXY}  (모든 데이터는 메모리에만 있고, 종료하면 사라집니다)`,
);

const stop = async () => {
  await vite.close();
  mock.server.close();
  process.exit(0);
};
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
