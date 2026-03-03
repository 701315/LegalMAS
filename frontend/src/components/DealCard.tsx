// =============================================================
// src/components/DealCard.tsx
// Карточка сделки для списка (DealListPage).
// =============================================================

import React from "react";
import type { Deal } from "../types";
import { timeAgo } from "../utils";

interface Props {
  deal: Deal;
  onClick?: () => void;
}

/**
 * Простая карточка сделки:
 * - название
 * - статус
 * - последний run (по полю last_run_id пока только текст)
 * - время обновления
 */
const DealCard: React.FC<Props> = ({ deal, onClick }) => {
  return (
    <div
      className="bg-white rounded-lg border p-4 cursor-pointer hover:shadow-sm transition-shadow"
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-base font-semibold text-gray-900">
          {deal.name}
        </h2>
        <span className="text-xs text-gray-500">
          #{deal.id}
        </span>
      </div>

      <p className="text-xs text-gray-500 mb-2">
        Статус: {deal.status}
      </p>

      {deal.last_run_id && (
        <p className="text-xs text-gray-500">
          Последний анализ: run {deal.last_run_id}
        </p>
      )}

      <p className="text-xs text-gray-400 mt-2">
        Обновлено: {timeAgo(deal.updated_at)}
      </p>
    </div>
  );
};

export default DealCard;
