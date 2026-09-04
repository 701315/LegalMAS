import React, { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

const ScrollToAnchor: React.FC = () => {
  const location = useLocation();
  const lastHashRef = useRef<string>("");

  useEffect(() => {
    const { hash } = location;

    if (!hash) {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      lastHashRef.current = "";
      return;
    }

    const id = hash.slice(1);
    lastHashRef.current = id;

    let retries = 0;
    const maxRetries = 16;

    let retryTimeout: number | undefined;
    let secondPassTimeout: number | undefined;
    let rafId: number | undefined;

    const tryScroll = () => {
      const currentId = lastHashRef.current;
      if (!currentId) return;

      const element = document.getElementById(currentId);

      if (element) {
        rafId = window.requestAnimationFrame(() => {
          element.scrollIntoView({
            block: "start",
            inline: "nearest",
            behavior: "auto",
          });

          secondPassTimeout = window.setTimeout(() => {
            document.getElementById(currentId)?.scrollIntoView({
              block: "start",
              inline: "nearest",
              behavior: "auto",
            });
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
      if (retryTimeout) window.clearTimeout(retryTimeout);
      if (secondPassTimeout) window.clearTimeout(secondPassTimeout);
      if (rafId) window.cancelAnimationFrame(rafId);
    };
  }, [location]);

  return null;
};

export default ScrollToAnchor;


