// Node(fetch) 의 TCP 연결만 127.0.0.1:8080 -> 127.0.0.1:<IT_PORT> 로 돌린다. 요청의 Host/Origin 은 그대로 127.0.0.1:8080 이다.
// 호스트에 8080 포트를 열지 않고(바이트 중계 프로세스 없이) nginx 의 Host 허용 목록을 통과하기 위한 시험 전용 전처리다.
// 사용: NODE_OPTIONS="--require /경로/redirect8080.cjs" IT_REDIRECT_TARGET=18080 IT_FE_DIR=<프런트 사본> node ...
const path = require('node:path');
const target = String(process.env.IT_REDIRECT_TARGET || '18080');
const undici = require(path.join(process.env.IT_FE_DIR, 'node_modules', 'undici'));
const connector = undici.buildConnector({});
const agent = new undici.Agent({
  connect: (opts, cb) => connector({ ...opts, port: String(opts.port) === '8080' ? target : opts.port }, cb),
});
undici.setGlobalDispatcher(agent);
