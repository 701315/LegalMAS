import React from "react";

export function useIsMobile(breakpoint = 1023) {
  const [isMobile, setIsMobile] = React.useState(false);

  React.useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);

    const update = () => setIsMobile(mq.matches);

    update();
    mq.addEventListener("change", update);

    return () => {
      mq.removeEventListener("change", update);
    };
  }, [breakpoint]);

  return isMobile;
}


