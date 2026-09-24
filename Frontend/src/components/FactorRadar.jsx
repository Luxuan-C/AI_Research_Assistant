import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis, 
  ResponsiveContainer,
} from "recharts";

const FACTORS = [
  { key: "H", label: "H", field: "H_hybrid_relevance", availability: null },
  { key: "Q", label: "Q", field: "Q_quality", availability: "Q" },
  { key: "I", label: "I", field: "I_citation_influence", availability: "I" },
  { key: "T", label: "T", field: "T_temporal_validity", availability: null },
  { key: "A", label: "A", field: "A_author_authority", availability: "A" },
];

export default function FactorRadar({ scoreBreakdown, factorAvailability }) {
  const data = FACTORS.map(({ key, label, field, availability }) => {
    const available =
      availability === null || Boolean(factorAvailability?.[availability]);
    const value = available ? Number(scoreBreakdown?.[field]) : null;
    return {
      factor: label,
      value: Number.isFinite(value) ? value : 0,
      available,
    };
  });

  const anyUnavailable = data.some((d) => !d.available);

  return (
    <div style={{ width: 180, height: 160 }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid />
          <PolarAngleAxis
            dataKey="factor"
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
          />
          <PolarRadiusAxis
                domain={[0, 1]}
                tick={false}          
                axisLine={false}     
            />
          {/* The PolarRadiusAxis is not rendered, so no numerical scales are displayed */}
          <Radar
            dataKey="value"
            stroke="var(--accent, #4f8cff)"
            fill="var(--accent, #4f8cff)"
            fillOpacity={0.35}
          />
        </RadarChart>
      </ResponsiveContainer>
      {anyUnavailable && (
        <div
          style={{
            fontSize: "11px",
            color: "var(--text-muted)",
            textAlign: "center",
            marginTop: "-6px",
          }}
        >
          Some factors are not available
        </div>
      )}
    </div>
  );
}
