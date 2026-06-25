// src/context/ScrollContext.tsx

import React, { createContext, useContext, useRef, useState } from "react";

interface ScrollContextValue {
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  scrolled: boolean;
  setScrolled: (v: boolean) => void;
  scrollToTop: () => void;
}

const ScrollContext = createContext<ScrollContextValue | null>(null);

export const ScrollProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [scrolled, setScrolled] = useState(false);

  const scrollToTop = () => {
    scrollContainerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <ScrollContext.Provider value={{ scrollContainerRef, scrolled, setScrolled, scrollToTop }}>
      {children}
    </ScrollContext.Provider>
  );
};

export const useScroll = () => {
  const ctx = useContext(ScrollContext);
  if (!ctx) throw new Error("useScroll must be used within ScrollProvider");
  return ctx;
};

