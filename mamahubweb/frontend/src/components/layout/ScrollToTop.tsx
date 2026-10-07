import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/** Reset window scroll when navigating between routes (SPA default keeps position). */
export function ScrollToTop() {
  const { pathname, search } = useLocation()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname, search])

  return null
}
