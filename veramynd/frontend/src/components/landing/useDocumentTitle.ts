import { useEffect } from 'react'

/** Set the browser tab title while a public page is mounted. */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    const previous = document.title
    document.title = title
    return () => {
      document.title = previous
    }
  }, [title])
}

export default useDocumentTitle
