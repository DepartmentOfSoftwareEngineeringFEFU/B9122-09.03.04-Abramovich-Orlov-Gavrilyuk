import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/Layout/AppLayout';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { PublicHomePage } from './pages/PublicHomePage';
import { WizardPage } from './pages/WizardPage';
import { EditPlanPage } from './pages/EditPlanPage';
import { PendingUsersPage } from './pages/PendingUsersPage';
import { StitchingPage } from './pages/StitchingPage';
import { TransitionsPage } from './pages/TransitionsPage';
import { RouteTestPage } from './pages/RouteTestPage';
import { AdminBuildingsPage } from './pages/AdminBuildingsPage';
import { BuildingAssemblyPage } from './pages/BuildingAssemblyPage';
import { VerticalStitchingPage } from './pages/VerticalStitchingPage';
import { Multifloor3DRoutesPage } from './pages/Multifloor3DRoutesPage';
import { BuildingScenePage } from './pages/BuildingScenePage';
import { FloorViewerPage } from './pages/FloorViewerPage';
import { FloorEditorPage } from './pages/FloorEditorPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<PublicHomePage />} />
      <Route path="/viewer" element={<FloorViewerPage />} />
      <Route path="/3d-routes" element={<Multifloor3DRoutesPage variant="public" />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/admin" element={<AppLayout />}>
        <Route index element={<AdminBuildingsPage />} />
        <Route path="pending-users" element={<PendingUsersPage />} />
        <Route path="stitching" element={<StitchingPage />} />
        <Route path="buildings" element={<Navigate to="/admin" replace />} />
      </Route>
      <Route path="/admin/buildings/:id/assembly" element={<BuildingAssemblyPage />} />
      <Route path="/admin/buildings/:id/scene" element={<BuildingScenePage />} />
      <Route path="/admin/vertical-stitching" element={<VerticalStitchingPage />} />
      <Route path="/admin/3d-routes" element={<Multifloor3DRoutesPage variant="admin" />} />
      <Route path="/admin/floor-editor" element={<FloorEditorPage />} />
      <Route path="/admin/transitions" element={<TransitionsPage />} />
      <Route path="/admin/transitions/:buildingId" element={<TransitionsPage />} />
      <Route path="/admin/route-test" element={<RouteTestPage />} />
      <Route path="/admin/edit/:id" element={<EditPlanPage />} />
      <Route path="/upload" element={<WizardPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
