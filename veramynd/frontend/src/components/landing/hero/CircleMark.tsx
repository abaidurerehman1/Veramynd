const RADIUS = 43
const STEP = 18.5
const COUNT = 5
const STROKE = 1.4

export function CircleMark() {
  const pad = STROKE / 2
  const width = (COUNT - 1) * STEP + RADIUS * 2 + STROKE
  const height = RADIUS * 2 + STROKE

  return (
    <svg
      className="fs-circle-mark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
    >
      <g fill="none" stroke="#000" strokeWidth={STROKE}>
        {Array.from({ length: COUNT }, (_, i) => (
          <circle key={i} cx={pad + RADIUS + i * STEP} cy={pad + RADIUS} r={RADIUS} />
        ))}
      </g>
    </svg>
  )
}

export default CircleMark
