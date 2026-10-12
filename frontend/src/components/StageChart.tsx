import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { StageMetric } from "../types";
import { formatStage } from "../utils/format";

export function StageChart({ data }: { data: StageMetric[] }) {
  const chartData = data.map((item) => ({
    ...item,
    label: formatStage(item.stage),
  }));

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={chartData}
          margin={{ top: 10, right: 8, bottom: 0, left: -16 }}
        >
          <CartesianGrid
            vertical={false}
            stroke="#edf0eb"
            strokeDasharray="4 5"
          />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#8b918c", fontSize: 11 }}
            interval={0}
            angle={-28}
            textAnchor="end"
            height={52}
          />
          <YAxis
            yAxisId="count"
            allowDecimals={false}
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#8b918c", fontSize: 11 }}
          />
          <YAxis yAxisId="percent" orientation="right" hide domain={[0, 100]} />
          <Tooltip
            cursor={{ fill: "#f7f8f5" }}
            contentStyle={{
              border: "1px solid #e8ebe6",
              borderRadius: 12,
              boxShadow: "0 12px 32px rgba(25, 35, 28, .08)",
              fontSize: 12,
            }}
            formatter={(value, name) => [
              name === "lead_count" ? (value ?? "—") : value == null ? "—" : `${value}%`,
              name === "lead_count" ? "Leads" : "Share of dataset",
            ]}
            labelStyle={{ color: "#202521", fontWeight: 650, marginBottom: 5 }}
          />
          <Bar
            yAxisId="count"
            dataKey="lead_count"
            fill="#c9f365"
            radius={[5, 5, 0, 0]}
            maxBarSize={34}
          />
          <Line
            yAxisId="percent"
            dataKey="percentage_of_total"
            type="monotone"
            stroke="#454d47"
            strokeWidth={2}
            dot={{ r: 3, fill: "#454d47", strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
