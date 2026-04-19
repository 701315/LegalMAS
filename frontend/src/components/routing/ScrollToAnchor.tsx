import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

const ScrollToAnchor: React.FC = () => {
  const location = useLocation();
  const lastHashRef = useRef<string>("");

  useEffect(() => {
    const { hash } = location;
    const HEADER_OFFSET = 72;

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
    const maxRetries = 16;

    let retryTimeout: number | undefined;
    let secondPassTimeout: number | undefined;
    let rafId: number | undefined;

    const scrollToTarget = (element: HTMLElement) => {
      const elementTop = element.getBoundingClientRect().top + window.scrollY;
      const targetTop = Math.max(elementTop - HEADER_OFFSET, 0);

      window.scrollTo({
        top: targetTop,
        left: 0,
        behavior: "auto",
      });
    };

    const tryScroll = () => {
      const currentId = lastHashRef.current;
      if (!currentId) return;

      const element = document.getElementById(currentId);

      if (element) {
        rafId = window.requestAnimationFrame(() => {
          scrollToTarget(element);

          secondPassTimeout = window.setTimeout(() => {
            const refreshedElement = document.getElementById(currentId);
            if (refreshedElement) {
              scrollToTarget(refreshedElement);
            }
            lastHashRef.current = "";
          }, 220);
        });

        return;
      }

      if (retries < maxRetries) {
        retries += 1;
        retryTimeout = window.setTimeout(tryScroll, 100);
      }
    };

    const initialTimeout = window.setTimeout(tryScroll, 120);

    return () => {
      window.clearTimeout(initialTimeout);

      if (retryTimeout) {
        window.clearTimeout(retryTimeout);
      }

      if (secondPassTimeout) {
        window.clearTimeout(secondPassTimeout);
      }

      if (rafId) {
        window.cancelAnimationFrame(rafId);
      }
    };
  }, [location]);

  return null;
};

export default ScrollToAnchor;

