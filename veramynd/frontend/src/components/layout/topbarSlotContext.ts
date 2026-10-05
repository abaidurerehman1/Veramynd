import { createContext } from 'react'

export type TopbarSlotState = {
  target: HTMLElement | null
  setClaimed: (claimed: boolean) => void
}

export const TopbarSlotContext = createContext<TopbarSlotState>({ target: null, setClaimed: () => {} })
