import rawProfiles from '../../../character-profiles.json'
import type { AgentName } from '../../types'

export type HairStyle = 'side' | 'crop' | 'bob' | 'swept' | 'short' | 'wave'

export interface CharacterProfile {
  skin: string
  hair: string
  jacket: string
  shirt: string
  trousers: string
  shoes: string
  accent: string
  hairStyle: HairStyle
}

export const CHARACTER_PROFILES = rawProfiles as Record<AgentName, CharacterProfile>
