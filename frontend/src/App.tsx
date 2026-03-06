// =============================================================
// src/App.tsx
// Основное приложение MAS-DD фронта: Login -> DealList -> Deal.
// =============================================================

import "./App.css";
import { Routes, Route, Navigate, useParams, useNavigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DealListPage from "./pages/DealListPage";
import DealPage from "./pages/DealPage";
import { useDeal } from "./api/deals";

function DealRouteWrapper() {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  const { data: deal, isLoading } = useDeal(dealId ?? null);

  const handleBackToDeals = () => {
    navigate("/deals");
  };

  if (isLoading || !deal) {
    return (
      <div className="p-6 text-center text-gray-500">
        Загружаем данные сделки…
      </div>
    );
  }

  return (
    <div>
      {/* Кнопка "Назад к сделкам" */}
      <div className="px-4 pt-4">
        <button
          type="button"
          onClick={handleBackToDeals}
          className="text-sm text-blue-600 hover:underline"
        >
          ← Назад к списку сделок
        </button>
      </div>
      <DealPage deal={deal} />
    </div>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Routes>
        {/* Страница логина */}
        <Route path="/login" element={<LoginPage onLoggedIn={() => { /* позже можно редиректить */ }} />} />

        {/* Список сделок */}
        <Route path="/deals" element={<DealListPage />} />

        {/* Детали сделки */}
        <Route path="/deals/:dealId" element={<DealRouteWrapper />} />

        {/* Редирект по умолчанию */}
        <Route path="*" element={<Navigate to="/deals" replace />} />
      </Routes>
    </div>
  );
}

export default App;
