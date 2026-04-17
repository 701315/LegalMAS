import React from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";
import { marketingTheme } from "../marketingTheme";

interface MarketingButtonProps {
  children: React.ReactNode;
  to?: string;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "tertiary";
  className?: string;
}

const MarketingButton: React.FC<MarketingButtonProps> = ({
  children,
  to,
  onClick,
  variant = "primary",
  className,
}) => {
  const classes = clsx(marketingTheme.button[variant], className);

  if (to) {
    return (
      <Link to={to} className={classes}>
        {children}
      </Link>
    );
  }

  return (
    <button onClick={onClick} className={classes}>
      {children}
    </button>
  );
};

export default MarketingButton;

