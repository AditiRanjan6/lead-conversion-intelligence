import type { LeadStage } from "../types";

const numberFormatter = new Intl.NumberFormat("en-US");
const amountFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

export function formatAmount(value: number): string {
  return amountFormatter.format(value);
}

export function formatPercent(value: number): string {
  return `${value.toFixed(2).replace(/\.00$/, "")}%`;
}

export function formatStage(stage: LeadStage): string {
  const labels: Record<LeadStage, string> = {
    new: "New",
    contacted: "Contacted",
    qualified: "Qualified",
    proposal: "Proposal",
    negotiation: "Negotiation",
    closed_won: "Closed won",
    closed_lost: "Closed lost",
  };
  return labels[stage];
}
