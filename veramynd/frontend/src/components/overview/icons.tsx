// Small icon set for the Overview dashboard. Colour glyphs echo the multi-colour app badges in the design.

type P = { size?: number }

export function SearchIcon({ size = 22 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" strokeLinecap="round" />
    </svg>
  )
}

export function PlusIcon({ size = 22 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M12 4v16M4 12h16" strokeLinecap="round" />
    </svg>
  )
}

export function ChevronDownIcon({ size = 16 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="m5 9 7 7 7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function HomeIcon({ size = 22 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M4 10.5 12 4l8 6.5V20h-5v-6H9v6H4z" strokeLinejoin="round" />
    </svg>
  )
}

export function GaugeIcon({ size = 22 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M4.5 17.5a8.5 8.5 0 1 1 15 0" strokeLinecap="round" />
      <path d="m12 13 4-4" strokeLinecap="round" />
      <path d="M8 17.5h8" strokeLinecap="round" />
    </svg>
  )
}

export function PeopleIcon({ size = 22 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="12" cy="8" r="3" />
      <circle cx="5.5" cy="10" r="2.2" />
      <circle cx="18.5" cy="10" r="2.2" />
      <path d="M7 19a5 5 0 0 1 10 0M2 18.5a3.6 3.6 0 0 1 4.5-3.4M22 18.5a3.6 3.6 0 0 0-4.5-3.4" strokeLinecap="round" />
    </svg>
  )
}

export function CalendarIcon({ size = 22 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2.5" />
      <path d="M8 3v4M16 3v4M4 10h16" strokeLinecap="round" />
      <path d="M8.5 13.5h1M11.5 13.5h1M14.5 13.5h1M8.5 16.5h1M11.5 16.5h1" strokeLinecap="round" />
    </svg>
  )
}

export function ChatIcon({ size = 22 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M12 20a8 8 0 1 0-7-4.1L4 20l4.1-1A8 8 0 0 0 12 20Z" strokeLinejoin="round" />
      <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" strokeLinecap="round" strokeWidth="2.2" />
    </svg>
  )
}

/** Full alignment: four-colour ring around a check. */
export function FullBadge({ size = 36 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" aria-hidden="true">
      <path d="M18 3a15 15 0 0 1 15 15h-6a9 9 0 0 0-9-9z" fill="#3b70f0" />
      <path d="M33 18a15 15 0 0 1-15 15v-6a9 9 0 0 0 9-9z" fill="#14dffe" />
      <path d="M18 33A15 15 0 0 1 3 18h6a9 9 0 0 0 9 9z" fill="#d09149" />
      <path d="M3 18A15 15 0 0 1 18 3v6a9 9 0 0 0-9 9z" fill="#ff80d5" />
      <path d="m13.5 18.2 3 3 6-6.2" fill="none" stroke="#000000" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Partial alignment: half-filled disc. */
export function PartialBadge({ size = 36 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="14" fill="#ebf1fe" />
      <path d="M18 4a14 14 0 0 1 0 28z" fill="#d09149" />
      <path d="M18 4a14 14 0 0 0-12.1 21L18 18z" fill="#14dffe" />
      <circle cx="18" cy="18" r="5" fill="#fff" />
    </svg>
  )
}

/** Review queue: flag. */
export function ReviewBadge({ size = 36 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" aria-hidden="true">
      <rect x="7" y="4" width="4" height="29" rx="2" fill="#000000" />
      <path d="M11 6h17l-4.5 7L28 20H11z" fill="#ff80d5" />
      <path d="M11 6h9v14h-9z" fill="#d09149" />
    </svg>
  )
}

/** Standards cited: target. */
export function CitedBadge({ size = 36 }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="15" fill="#14dffe" />
      <circle cx="18" cy="18" r="10.5" fill="#fff" />
      <circle cx="18" cy="18" r="6.5" fill="#3b70f0" />
      <circle cx="18" cy="18" r="2.5" fill="#d09149" />
    </svg>
  )
}

/** Review-list status glyphs inside the white circle. */
export function StatusGlyph({ status }: { status: 'full' | 'partial' | 'none' | 'escalated' }) {
  const color = { full: '#3b70f0', partial: '#d09149', none: '#9a9a9a', escalated: '#c4483b' }[status]
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <rect x="1" y="1" width="24" height="24" rx="7" fill={color} />
      {status === 'escalated' ? (
        <path d="M13 7v7M13 18.5h.01" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
      ) : status === 'full' ? (
        <path d="m8 13.4 3.2 3.1L18 9.8" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      ) : status === 'partial' ? (
        <path d="M13 6.5a6.5 6.5 0 0 1 0 13z" fill="#fff" />
      ) : (
        <path d="M8.5 13h9" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
      )}
    </svg>
  )
}
