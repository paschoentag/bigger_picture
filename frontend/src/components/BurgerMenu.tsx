import { useEffect, useRef, useState } from 'react'

/** Account-bar overflow menu: Admin (if applicable), My Stats, Community Stats, Leaderboard, Log out. */
export default function BurgerMenu({
  adminLabel,
  onOpenAdmin,
  onOpenStats,
  onOpenCommunityStats,
  onOpenLeaderboard,
  onLogout,
}: {
  adminLabel: string
  onOpenAdmin: () => void
  onOpenStats: () => void
  onOpenCommunityStats: () => void
  onOpenLeaderboard: () => void
  onLogout: () => void
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const runAndClose = (action: () => void) => () => {
    setOpen(false)
    action()
  }

  return (
    <div className="burger-menu" ref={containerRef}>
      <button
        type="button"
        className="burger-menu-toggle"
        aria-label="Menu"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span />
        <span />
        <span />
      </button>
      {open && (
        <div className="burger-menu-dropdown" role="menu">
          <button type="button" role="menuitem" onClick={runAndClose(onOpenAdmin)}>
            {adminLabel}
          </button>
          <button type="button" role="menuitem" onClick={runAndClose(onOpenStats)}>
            My Stats
          </button>
          <button type="button" role="menuitem" onClick={runAndClose(onOpenCommunityStats)}>
            Community Stats
          </button>
          <button type="button" role="menuitem" onClick={runAndClose(onOpenLeaderboard)}>
            Leaderboard
          </button>
          <button type="button" role="menuitem" onClick={runAndClose(onLogout)}>
            Log out
          </button>
        </div>
      )}
    </div>
  )
}
