import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { ApiClient } from './api/client';
import { App } from './app/App';
import { Providers } from './app/providers';
import './styles/index.css';

const client = new ApiClient();
const root = document.getElementById('root');
if (!root) throw new Error('root 요소가 없습니다');

// HashRouter: 새로고침해도 서버의 SPA 대체 응답(try_files) 설정에 의존하지 않는다
createRoot(root).render(
  <StrictMode>
    <Providers client={client}>
      <HashRouter>
        <App />
      </HashRouter>
    </Providers>
  </StrictMode>,
);
