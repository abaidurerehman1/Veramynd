import type React from 'react'

// Line art drawn in the reference card's own coordinate space (253 × 313), so it scales with the card.
type Props = { children: React.ReactNode }

function Art({ children }: Props) {
  return (
    <svg className="ln-art" viewBox="0 0 253 313" preserveAspectRatio="none" aria-hidden="true">
      <g fill="none" stroke="#000" strokeWidth="1">
        {children}
      </g>
    </svg>
  )
}

export function CornerArcArt() {
  return (
    <Art>
      <path d="M144 313V176H253" />
      <path d="M252 176A108 108 0 0 0 144 284" />
    </Art>
  )
}

export function TargetArt() {
  return (
    <Art>
      <circle cx="214" cy="255" r="76" />
      <circle cx="214" cy="255" r="28" />
      <path d="M221 156V227.9M221 282.1V313M117 262H186.9M240.5 246H253" />
    </Art>
  )
}

export function LensArt() {
  return (
    <Art>
      <path d="M148.1 178.3A42 42 0 1 0 139.2 214" />
      <path d="M123.4 175.5A20 20 0 1 0 123.4 198.5" />
      <path d="M107 189H253" />
      <circle cx="253" cy="189" r="77" />
      <path d="M197 116L253 181M197 252L253 197" />
    </Art>
  )
}
