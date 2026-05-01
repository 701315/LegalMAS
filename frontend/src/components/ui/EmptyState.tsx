// src/components/ui/EmptyState.tsx

import React from "react";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: React.ReactNode;
}

const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  action,
}) => {
  return (
    <div className="rounded border border-dashed border-gray-200 bg-gray-50 px-4 py-8 text-center">
      <div className="mx-auto max-w-md">
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        <p className="mt-2 text-xs leading-5 text-gray-500">{description}</p>

        {action && <div className="mt-4 flex justify-center">{action}</div>}
      </div>
    </div>
  );
};

export default EmptyState;

