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

export function formatStage(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
