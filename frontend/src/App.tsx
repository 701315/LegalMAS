// =============================================================
// src/App.tsx
// Основное приложение MAS-DD фронта: Login -> DealList -> Deal.
// =============================================================

import { useState } from "react";
import "./App.css";
import LoginPage from "./pages/LoginPage";
import DealListPage from "./pages/DealListPage";
import DealPage from "./pages/DealPage";
import { useDeal } from "./api/deals";

// Типы экранов (упрощённый роутинг без react-router)
type View = "login" | "deals" | "deal";

function App() {
  const [view, setView] = useState<View>("login");
  const [selectedDealId, setSelectedDealId] = useState<string | null>(null);

  // Подгружаем сделку только когда нужно
  const { data: selectedDeal } = useDeal(
    view === "deal" ? selectedDealId : null,
  );

  // Обработчик логина: после ввода API-ключа и роли идём к списку сделок
  const handleLoggedIn = () => {
    setView("deals");
  };

  // Обработчик выбора сделки в списке
  const handleSelectDeal = (dealId: string) => {
    setSelectedDealId(dealId);
    setView("deal");
  };

  // Обработчик "назад" со страницы сделки к списку
  const handleBackToDeals = () => {
    setView("deals");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {view === "login" && <LoginPage onLoggedIn={handleLoggedIn} />}

      {view === "deals" && <DealListPage onSelectDeal={handleSelectDeal} />}

      {view === "deal" && selectedDeal && (
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
          <DealPage deal={selectedDeal} />
        </div>
      )}

      {view === "deal" && !selectedDeal && (
        <div className="p-6 text-center text-gray-500">
          Загружаем данные сделки…
        </div>
      )}
    </div>
  );
}

export default App;
