// =============================================================
// src/components/playbook/RefreshPlaybookButton.tsx
// Кнопка "Обновить на свежих инструкциях".
//
// Создаёт новую published-версию playbook через
// POST /api/v1/playbooks/{version_id}/refresh-as-new.
// Deals не переключаются, старая версия остаётся для аудита.
//
// Namespace i18n: "playbooks".
// =============================================================

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import client from "../../api/client";
import type { RefreshPlaybookAsNewResponse } from "../../types/playbooks";
import { getApiErrorMessage } from "../../utils/apiErrors";

import Button from "../ui/Button";
import ConfirmDialog from "../ConfirmDialog";
import InlineAlert from "../InlineAlert";

interface RefreshPlaybookButtonProps {
  versionId: string;
  /** Отображаемое имя версии — для текста подтверждения. */
  versionName?: string;
  disabled?: boolean;
  variant?: "primary" | "secondary";
  size?: "sm" | "md";
  onSuccess?: (response: RefreshPlaybookAsNewResponse) => void;
}

const RefreshPlaybookButton: React.FC<RefreshPlaybookButtonProps> = ({
  versionId,
  versionName,
  disabled = false,
  variant = "secondary",
  size = "sm",
  onSuccess,
}) => {
  const { t } = useTranslation("playbooks");
  const queryClient = useQueryClient();

  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation<
    RefreshPlaybookAsNewResponse,
    unknown,
    void
  >({
    mutationFn: async () => {
      const res = await client.post<RefreshPlaybookAsNewResponse>(
        `/api/v1/playbooks/${versionId}/refresh-as-new`,
      );
      return res.data;
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["playbooks"] });
      setIsConfirmOpen(false);
      setError(null);
      onSuccess?.(data);
    },
    onError: (err) => {
      setError(getApiErrorMessage(err, t("staleness.refresh.error")));
    },
  });

  const handleConfirm = () => {
    setError(null);
    mutation.mutate();
  };

  return (
    <>
      <Button
        type="button"
        variant={variant}
        size={size}
        onClick={() => {
          setError(null);
          setIsConfirmOpen(true);
        }}
        disabled={disabled || mutation.isPending}
        isLoading={mutation.isPending}
      >
        {t("staleness.refresh.button")}
      </Button>

      {error && !isConfirmOpen && (
        <div className="mt-2">
          <InlineAlert tone="error" message={error} />
        </div>
      )}

      <ConfirmDialog
        open={isConfirmOpen}
        title={t("staleness.refresh.confirmTitle")}
        description={t("staleness.refresh.confirmDescription", {
          name: versionName ?? versionId.slice(0, 8),
        })}
        confirmLabel={t("staleness.refresh.confirmLabel")}
        cancelLabel={t("staleness.refresh.cancelLabel")}
        confirmVariant="primary"
        confirmingLabel={t("staleness.refresh.confirmingLabel")}
        isConfirming={mutation.isPending}
        onConfirm={handleConfirm}
        onCancel={() => {
          if (!mutation.isPending) setIsConfirmOpen(false);
        }}
      />
    </>
  );
};

export default RefreshPlaybookButton;
