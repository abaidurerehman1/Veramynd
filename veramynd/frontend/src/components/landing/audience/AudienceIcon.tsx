import type { ReactElement } from 'react'

export type AudienceIconName = 'book' | 'checklist' | 'magnifier'

const ICONS: Record<AudienceIconName, ReactElement> = {
  // Open book: curriculum publishers.
  book: (
    <path d="M9 4.5C7.6 3.5 5.6 3 3 3v10.5c2.6 0 4.6.5 6 1.5 1.4-1 3.4-1.5 6-1.5V3c-2.6 0-4.6.5-6 1.5Zm-.75 1.3v7.4c-1.2-.6-2.7-.95-4.5-1.05V4.5c1.8.1 3.3.5 4.5 1.3Zm1.5 0c1.2-.8 2.7-1.2 4.5-1.3v7.65c-1.8.1-3.3.45-4.5 1.05Z" />
  ),
  // Checklist: alignment reviewers.
  checklist: (
    <path d="M2.5 4.3 3.6 3.2l1.1 1.1L6.9 2.1 8 3.2 4.7 6.5Zm0 6 1.1-1.1 1.1 1.1 2.2-2.2L8 9.2l-3.3 3.3ZM9.5 3.75h6v1.5h-6Zm0 6h6v1.5h-6Zm-7 4.5h13v1.5h-13Z" />
  ),
  // Magnifier: curriculum specialists.
  magnifier: (
    <path d="M7.75 2.5a5.25 5.25 0 0 1 4.16 8.45l3.84 3.84-1.06 1.06-3.84-3.84A5.25 5.25 0 1 1 7.75 2.5Zm0 1.5a3.75 3.75 0 1 0 0 7.5 3.75 3.75 0 0 0 0-7.5Z" />
  ),
}

export function AudienceIcon({ name }: { name: AudienceIconName }) {
  return (
    <span className="ro-icon" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="#fff">
        {ICONS[name]}
      </svg>
    </span>
  )
}

export default AudienceIcon
