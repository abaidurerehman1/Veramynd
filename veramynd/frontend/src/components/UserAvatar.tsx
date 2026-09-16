type Props = {
  name?: string | null
  avatarUrl?: string | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

function initialsFrom(name?: string | null) {
  return (name || 'VR')
    .split(/\s+/)
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export function UserAvatar({ name, avatarUrl, size = 'md', className = '' }: Props) {
  const sizeClass = size === 'lg' ? ' lg' : size === 'sm' ? ' sm' : ''
  if (avatarUrl) {
    return (
      <div className={`avatar has-photo${sizeClass} ${className}`.trim()} aria-hidden>
        <img src={avatarUrl} alt="" />
      </div>
    )
  }
  return (
    <div className={`avatar${sizeClass} ${className}`.trim()} aria-hidden>
      {initialsFrom(name)}
    </div>
  )
}
