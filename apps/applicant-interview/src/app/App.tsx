import { Navigate, NavLink, Route, Routes } from "react-router-dom";

import { applicantFeatureRoutes } from "./featureRoutes";

export function App() {
  const defaultPath = applicantFeatureRoutes[0].path;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Interview Evidence Platform</p>
          <p className="app-title">지원자 AI 면접</p>
          <p>안내와 동의를 확인한 뒤 안전하게 면접을 진행합니다.</p>
        </div>
        <nav aria-label="지원자 기능">
          <ul className="feature-navigation">
            {applicantFeatureRoutes.map((route) => (
              <li key={route.path}>
                <NavLink
                  to={route.path}
                  className={({ isActive }) =>
                    isActive ? "feature-link active" : "feature-link"
                  }
                >
                  {route.title}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <section className="feature-content" aria-label="선택한 지원자 기능">
        <Routes>
          <Route index element={<Navigate to={defaultPath} replace />} />
          {applicantFeatureRoutes.map((route) => (
            <Route key={route.path} path={route.path} element={route.element} />
          ))}
          <Route path="*" element={<Navigate to={defaultPath} replace />} />
        </Routes>
      </section>
    </div>
  );
}
