import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

/**
 * Глобальный обработчик переходов по якорям.
 *
 * Работает для ссылок вида:
 *   - "/#capabilities"
 *   - "/#use-cases"
 *   - "/security#privacy"
 *   - "/tech#pipeline"
 *
 * При смене location:
 *   - если есть hash → скроллит к соответствующему элементу с учётом высоты header;
 *   - если hash нет → скроллит страницу к началу (top: 0).
 */
const ScrollToAnchor: React.FC = () => {
  const location = useLocation();
  const lastHashRef = useRef<string>("");

  useEffect(() => {
    const { hash } = location;
    const HEADER_OFFSET = 96;

    if (!hash) {
      window.scrollTo({
        top: 0,
        left: 0,
        behavior: "auto",
      });
      lastHashRef.current = "";
      return;
    }

    const id = hash.replace("#", "");
    lastHashRef.current = id;

    let retries = 0;
    const maxRetries = 12;
    let retryTimeout: number | undefined;

    const tryScroll = () => {
      const currentId = lastHashRef.current;
      if (!currentId) return;

      const element = document.getElementById(currentId);

      if (element) {
        const elementTop = element.getBoundingClientRect().top + window.scrollY;
        const targetTop = Math.max(elementTop - HEADER_OFFSET, 0);

        window.scrollTo({
          top: targetTop,
          left: 0,
          behavior: "auto",
        });

        lastHashRef.current = "";
        return;
      }

      if (retries < maxRetries) {
        retries += 1;
        retryTimeout = window.setTimeout(tryScroll, 80);
      }
    };

    const initialTimeout = window.setTimeout(tryScroll, 60);

    return () => {
      window.clearTimeout(initialTimeout);
      if (retryTimeout) {
        window.clearTimeout(retryTimeout);
      }
    };
  }, [location]);

  return null;
};

export default ScrollToAnchor;


