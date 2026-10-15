import { Link, Route, Routes } from 'react-router-dom';
import { EmptyState, PageHead } from '../components';
import { ko } from '../i18n/ko';
import { AuthGate } from './AuthGate';
import { Layout } from './Layout';
import { HomePage } from '../pages/HomePage';
import { VideosPage } from '../pages/VideosPage';
import { VideoDetailPage } from '../pages/VideoDetailPage';
import { BulkApprovePage } from '../pages/BulkApprovePage';
import { BatchesPage } from '../pages/BatchesPage';
import { BatchDetailPage } from '../pages/BatchDetailPage';
import { HistoryPage } from '../pages/HistoryPage';
import { ReportsPage } from '../pages/ReportsPage';
import { SettingsPage } from '../pages/SettingsPage';

function NotFound() {
  return (
    <>
      <PageHead title={ko.app.notFoundTitle} />
      <EmptyState title={ko.app.notFoundTitle} action={<Link to="/">{ko.app.goHome}</Link>}>
        {ko.app.notFoundBody}
      </EmptyState>
    </>
  );
}

export function App() {
  return (
    <AuthGate>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="videos" element={<VideosPage />} />
          <Route path="videos/:videoId" element={<VideoDetailPage />} />
          <Route path="bulk-approve" element={<BulkApprovePage />} />
          <Route path="batches" element={<BatchesPage />} />
          <Route path="batches/:batchId" element={<BatchDetailPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </AuthGate>
  );
}
