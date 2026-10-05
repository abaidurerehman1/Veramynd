import { useState, type FormEvent, type KeyboardEvent } from 'react'

type Props = {
  onAsk?: (query: string) => void
}

export function HeroSearch({ onAsk }: Props) {
  const [query, setQuery] = useState('')

  const submit = () => {
    const trimmed = query.trim()
    if (trimmed) onAsk?.(trimmed)
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit()
  }

  // Enter submits, Shift+Enter inserts a newline.
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form className="fs-search" role="search" onSubmit={handleSubmit}>
      <textarea
        className="fs-search__input"
        placeholder="Ask about the pipeline, verdicts, inputs or exports..."
        aria-label="Search the Veramynd documentation"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="submit" className="fs-search__button">
        Search the docs <span aria-hidden="true">→</span>
      </button>
    </form>
  )
}

export default HeroSearch
