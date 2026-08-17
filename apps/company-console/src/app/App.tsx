import { Navigate, NavLink, Route, Routes } from "react-router-dom";

import { companyFeatureRoutes } from "./featureRoutes";

export function App() {
  const defaultPath = companyFeatureRoutes[0].path;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Interview Evidence Platform</p>
          <p className="app-title">기업 면접 관리</p>
          <p>채용 기준과 실제 답변 근거를 한 흐름에서 관리합니다.</p>
        </div>
        <nav aria-label="기업 기능">
          <ul className="feature-navigation">
            {companyFeatureRoutes.map((route) => (
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

      <section className="feature-content" aria-label="선택한 기업 기능">
        <Routes>
          <Route index element={<Navigate to={defaultPath} replace />} />
          {companyFeatureRoutes.map((route) => (
            <Route key={route.path} path={route.path} element={route.element} />
          ))}
          <Route path="*" element={<Navigate to={defaultPath} replace />} />
        </Routes>
      </section>
    </div>
  );
}
