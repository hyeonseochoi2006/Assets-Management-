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

export const CHARACTER_PROFILES: Record<AgentName, CharacterProfile> = {
  CIO: {
    skin: '#d8aa8d',
    hair: '#242832',
    jacket: '#536fae',
    shirt: '#dce5f3',
    trousers: '#222b3a',
    shoes: '#171b23',
    accent: '#8ca8ec',
    hairStyle: 'side',
  },
  Analysis: {
    skin: '#c99173',
    hair: '#2d241f',
    jacket: '#4f89a9',
    shirt: '#e4edf1',
    trousers: '#24303a',
    shoes: '#171c20',
    accent: '#72b5d5',
    hairStyle: 'crop',
  },
  Portfolio: {
    skin: '#e0b394',
    hair: '#342925',
    jacket: '#6d63b6',
    shirt: '#eeeaf7',
    trousers: '#29253d',
    shoes: '#181622',
    accent: '#9b8fe6',
    hairStyle: 'bob',
  },
  Risk: {
    skin: '#b9785d',
    hair: '#191b20',
    jacket: '#b46e53',
    shirt: '#f2e5dd',
    trousers: '#342923',
    shoes: '#1d1815',
    accent: '#e19a78',
    hairStyle: 'swept',
  },
  Execution: {
    skin: '#d4a184',
    hair: '#49372c',
    jacket: '#4b987b',
    shirt: '#e4f0eb',
    trousers: '#20342e',
    shoes: '#151d1a',
    accent: '#72c5a5',
    hairStyle: 'short',
  },
  Briefing: {
    skin: '#e1b99c',
    hair: '#3b292b',
    jacket: '#9567ac',
    shirt: '#f1e9f3',
    trousers: '#35263b',
    shoes: '#1d1720',
    accent: '#c18bd8',
    hairStyle: 'wave',
  },
}
