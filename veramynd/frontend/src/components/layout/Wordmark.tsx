/** Veramynd logo as on the landing page: two-circle mark + name, with an optional product label. */
export function Wordmark({ size = 18, product }: { size?: number; product?: string }) {
  const mark = Math.round(size * 1.1)
  return (
    <span className="wordmark" style={{ fontSize: size }} aria-label={`Veramynd${product ? ` ${product}` : ''}`}>
      <svg className="wordmark-mark" width={mark * 1.6} height={mark} viewBox="0 0 37 22" aria-hidden="true">
        <circle cx="26.3" cy="11" r="9.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="10.5" cy="11" r="10.5" fill="currentColor" />
      </svg>
      <span className="name">Veramynd</span>
      {product ? <span className="prod">{product}</span> : null}
    </span>
  )
}

export default Wordmark
