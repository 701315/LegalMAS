import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

export type HeaderTheme = "light" | "dark";

interface ScrollContextValue {
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  scrolled: boolean;
  setScrolled: React.Dispatch<React.SetStateAction<boolean>>;
  headerTheme: HeaderTheme;
  setHeaderTheme: React.Dispatch<React.SetStateAction<HeaderTheme>>;
  scrollToTop: () => void;
}

const ScrollContext = createContext<ScrollContextValue | null>(null);

export const ScrollProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const [headerTheme, setHeaderTheme] = useState<HeaderTheme>("dark");

  const scrollToTop = useCallback(() => {
    scrollContainerRef.current?.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }, []);

  const value = useMemo<ScrollContextValue>(
    () => ({
      scrollContainerRef,
      scrolled,
      setScrolled,
      headerTheme,
      setHeaderTheme,
      scrollToTop,
    }),
    [scrolled, headerTheme, scrollToTop]
  );

  return (
    <ScrollContext.Provider value={value}>{children}</ScrollContext.Provider>
  );
};

export const useScroll = (): ScrollContextValue => {
  const ctx = useContext(ScrollContext);
  if (!ctx) throw new Error("useScroll must be used within ScrollProvider");
  return ctx;
};

