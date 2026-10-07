interface Point {
  label: string
  value: number
}

export function SalesLineChart({ data }: { data: Point[] }) {
  const width = 560
  const height = 220
  const pad = { top: 16, right: 16, bottom: 32, left: 16 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom
  const max = Math.max(...data.map((d) => d.value), 1)

  const points = data.map((d, i) => {
    const x = pad.left + (i / Math.max(data.length - 1, 1)) * innerW
    const y = pad.top + innerH - (d.value / max) * innerH
    return { x, y, ...d }
  })

  const line = points.map((p) => `${p.x},${p.y}`).join(' ')
  const area = `${points[0]?.x ?? pad.left},${pad.top + innerH} ${line} ${points[points.length - 1]?.x ?? pad.left},${pad.top + innerH}`

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Sales overview chart">
      <defs>
        <linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#E91E63" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#E91E63" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <line
          key={t}
          x1={pad.left}
          x2={width - pad.right}
          y1={pad.top + innerH * t}
          y2={pad.top + innerH * t}
          stroke="#eef2f7"
          strokeWidth="1"
        />
      ))}
      {points.length > 1 && <polygon points={area} fill="url(#salesFill)" />}
      {points.length > 1 && (
        <polyline points={line} fill="none" stroke="#E91E63" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {points.map((p) => (
        <g key={p.label}>
          <circle cx={p.x} cy={p.y} r="4" fill="#E91E63" />
          <text x={p.x} y={height - 8} textAnchor="middle" className="fill-[#94a3b8] text-[10px]">
            {p.label}
          </text>
        </g>
      ))}
    </svg>
  )
}

interface Slice {
  label: string
  value: number
  color: string
}

export function CategoryDonutChart({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0) || 1
  let cursor = 0
  const radius = 54
  const cx = 70
  const cy = 70

  const arcs = slices.map((slice) => {
    const start = cursor
    const angle = (slice.value / total) * 360
    cursor += angle
    const end = cursor
    const large = angle > 180 ? 1 : 0
    const startRad = ((start - 90) * Math.PI) / 180
    const endRad = ((end - 90) * Math.PI) / 180
    const x1 = cx + radius * Math.cos(startRad)
    const y1 = cy + radius * Math.sin(startRad)
    const x2 = cx + radius * Math.cos(endRad)
    const y2 = cy + radius * Math.sin(endRad)
    const d = `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${large} 1 ${x2} ${y2} Z`
    return { ...slice, d, pct: Math.round((slice.value / total) * 100) }
  })

  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
      <svg viewBox="0 0 140 140" className="h-36 w-36 shrink-0" role="img" aria-label="Sales by category">
        {arcs.map((arc) => (
          <path key={arc.label} d={arc.d} fill={arc.color} />
        ))}
        <circle cx={cx} cy={cy} r="30" fill="white" />
      </svg>
      <div className="space-y-2 text-sm">
        {arcs.map((arc) => (
          <div key={arc.label} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: arc.color }} />
            <span className="text-[#475569]">{arc.label}</span>
            <span className="font-semibold text-[#0f172a]">{arc.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
