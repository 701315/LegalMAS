// =============================================================
// src/components/new-project/Block4ModelConfig.tsx
//
// Блок 4 — Выбор профиля модели.
//
// Только выбор существующего профиля модели и применение к deal.
// Без создания/редактирования/удаления — полный
// ModelConfigManagerPanel остаётся нетронутым.
//
// Шаги:
//   1. Выбрать профиль из списка
//   2. Применить к проекту → PATCH /api/v1/deals/:dealId/model-config
//
// Блок не является обязательным для flow —
// если ничего не выбрано, используется профиль по умолчанию.
// =============================================================

import React from "react";
import { Cpu, Loader2 } from "lucide-react";

import client from "../../api/client";
import type { ModelConfig } from "../../types";
import { getApiErrorMessage } from "../../utils/apiErrors";

import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";

interface Block4ModelConfigProps {
  dealId: string;
  /** Текущий model_config_id из deal (может быть null) */
  currentConfigId: string | null;
  /** Текущее имя профиля из deal (может быть null) */
  currentConfigName: string | null;
  /** Вызывается после успешного применения */
  onApplied: (configId: string, configName: string) => void;
  /** Вызывается при пропуске шага */
  onSkipped: () => void;
}

const cardButtonClassName = [
  "w-full rounded-xl border px-3 py-2.5 text-left text-xs transition-colors",
  "focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-[var(--accent-primary)]/35",
  "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
].join(" ");

const cardIdleClassName =
  "border-[var(--border-soft)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-elevated-soft)]";

const cardActiveClassName =
  "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]";

const Block4ModelConfig: React.FC<Block4ModelConfigProps> = ({
  dealId,
  currentConfigId,
  currentConfigName,
  onApplied,
  onSkipped,
}) => {
  // ── Data state ────────────────────────────────────────────
  const [configs, setConfigs] = React.useState<ModelConfig[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  // ── Selection state ───────────────────────────────────────
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  // ── Apply state ───────────────────────────────────────────
  const [isApplying, setIsApplying] = React.useState(false);
  const [applyError, setApplyError] = React.useState<string | null>(null);

  const isLocked = isApplying;

  // ── Load data ─────────────────────────────────────────────
  React.useEffect(() => {
    let cancelled = false;

    async function loadConfigs() {
      setIsLoading(true);
      setLoadError(null);

      try {
        const res = await client.get<ModelConfig[]>("/api/v1/model-configs");

        if (cancelled) return;

        const items = res.data ?? [];
        setConfigs(items);

        // Преселект текущего профиля
        if (currentConfigId) {
          const exists = items.some(
            (c) => String(c.id) === String(currentConfigId),
          );

          if (exists) {
            setSelectedId(String(currentConfigId));
          }
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            getApiErrorMessage(
              err,
              "Не удалось загрузить профили моделей.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadConfigs();

    return () => {
      cancelled = true;
    };
  }, [currentConfigId]);

  // ── Derived ───────────────────────────────────────────────
  const isSameAsCurrent =
    currentConfigId !== null &&
    selectedId === String(currentConfigId);

  const canApply = !!selectedId && !isApplying && !isSameAsCurrent;

  // ── Handlers ──────────────────────────────────────────────
  const handleSelect = React.useCallback(
    (configId: string) => {
      if (isLocked) return;

      setApplyError(null);
      setSelectedId(configId);
    },
    [isLocked],
  );

  const handleApply = React.useCallback(async () => {
    if (!selectedId || isApplying) return;

    setIsApplying(true);
    setApplyError(null);

    try {
      await client.patch(`/api/v1/deals/${dealId}/model-config`, {
        model_config_id: selectedId,
      });

      const config = configs.find((c) => String(c.id) === selectedId);
      const name = config?.name ?? selectedId;

      onApplied(selectedId, name);
    } catch (err) {
      setApplyError(
        getApiErrorMessage(
          err,
          "Не удалось назначить профиль модели проекту.",
        ),
      );
    } finally {
      setIsApplying(false);
    }
  }, [configs, dealId, isApplying, onApplied, selectedId]);

  // ── Loading ───────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-4">
        <Loader2
          className="h-4 w-4 animate-spin text-[var(--accent-primary)]"
          aria-hidden="true"
        />
        <span className="text-sm text-[var(--text-muted)]">
          Загружаем профили моделей…
        </span>
      </div>
    );
  }

  // ── Load error ────────────────────────────────────────────
  if (loadError) {
    return <InlineAlert tone="error" message={loadError} />;
  }

  // ── Empty ─────────────────────────────────────────────────
  if (configs.length === 0) {
    return (
      <div className="space-y-3">
        <div className="subtle-panel px-4 py-3">
          <div className="flex items-start gap-3">
            <div
              className="mt-0.5 shrink-0 text-[var(--text-muted)]"
              aria-hidden="true"
            >
              <Cpu className="h-4 w-4" />
            </div>

            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Профили моделей не настроены
              </p>
              <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                Будет использован профиль по умолчанию. Базовые настройки
                подходят для большинства проектов. Создать профили можно в
                административном разделе.
              </p>
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onSkipped}
          >
            Продолжить с профилем по умолчанию
          </Button>
        </div>
      </div>
    );
  }

  // ── Main content ──────────────────────────────────────────
  return (
    <div className="space-y-4">
      {applyError ? <InlineAlert tone="error" message={applyError} /> : null}

      {/* ── Описание шага ────────────────────────────────── */}
      <div className="subtle-panel px-4 py-3">
        <div className="flex items-start gap-3">
          <div
            className="mt-0.5 shrink-0 text-[var(--text-muted)]"
            aria-hidden="true"
          >
            <Cpu className="h-4 w-4" />
          </div>

          <div className="min-w-0">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              Профиль модели определяет параметры семантического анализа
            </p>
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
              Базовые настройки уже установлены в системе и подходят для
              большинства проектов. Вы можете продолжить с профилем по
              умолчанию без дополнительных действий.
            </p>
            <p className="mt-2 text-[11px] leading-5 text-[var(--text-secondary)]">
              Если для вашего проекта нужны специфические настройки поиска и
              retrieval — выберите существующий профиль ниже или создайте новый
              в административном разделе.
            </p>
          </div>
        </div>
      </div>

      {/* Текущий профиль */}
      {currentConfigName ? (
        <div className="subtle-panel px-4 py-3">
          <p className="text-[11px] text-[var(--text-muted)]">
            Текущий профиль проекта:{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {currentConfigName}
            </span>
          </p>
        </div>
      ) : null}

      {/* Список профилей */}
      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Доступные профили
        </p>

        <ul className="max-h-64 space-y-1 overflow-y-auto">
          {configs.map((config) => {
            const configId = String(config.id);
            const isSelected = selectedId === configId;
            const isCurrent =
              currentConfigId !== null &&
              configId === String(currentConfigId);

            return (
              <li key={configId}>
                <button
                  type="button"
                  onClick={() => handleSelect(configId)}
                  disabled={isLocked}
                  className={[
                    cardButtonClassName,
                    isSelected ? cardActiveClassName : cardIdleClassName,
                    isLocked ? "cursor-not-allowed opacity-60" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{config.name}</span>

                    {isCurrent ? (
                      <span className="rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--color-success-text)]">
                        Текущий
                      </span>
                    ) : null}
                  </div>

                  {config.description ? (
                    <div className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                      {config.description}
                    </div>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Действия */}
      <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] pt-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onSkipped}
          disabled={isApplying}
        >
          Продолжить с профилем по умолчанию
        </Button>

        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={handleApply}
          disabled={!canApply}
          isLoading={isApplying}
        >
          {isSameAsCurrent ? "Уже применён" : "Выбрать для проекта"}
        </Button>
      </div>
    </div>
  );
};

export default Block4ModelConfig;


