// src/components/ui/LoadingBlock.tsx

import React from "react";

interface LoadingBlockProps {
  text?: string;
  rows?: number;
}

const LoadingBlock: React.FC<LoadingBlockProps> = ({
  text = "Загрузка данных…",
  rows = 3,
}) => {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="rounded border border-gray-200 bg-white p-4"
    >
      <span className="sr-only">{text}</span>

      <div className="animate-pulse space-y-2">
        {Array.from({ length: rows }).map((_, index) => (
          <div
            key={index}
            className="h-4 rounded bg-gray-200"
            style={{
              width:
                index % 3 === 0 ? "92%" : index % 3 === 1 ? "78%" : "64%",
            }}
          />
        ))}
      </div>
    </div>
  );
};

export default LoadingBlock;


