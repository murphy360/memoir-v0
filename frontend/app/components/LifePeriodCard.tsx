import type { ReactNode } from "react";
import type { LifePeriod } from "../types";

type LifePeriodCardProps = {
  period: LifePeriod;
  isHighlighted: boolean;
  children: ReactNode;
};

export function LifePeriodCard({
  period,
  isHighlighted,
  children,
}: LifePeriodCardProps) {
  return (
    <article
      id={`period-card-${period.id}`}
      className={`memory${isHighlighted ? " focusPulse" : ""}`}
    >
      {children}
    </article>
  );
}
