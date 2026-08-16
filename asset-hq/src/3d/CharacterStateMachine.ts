import type { CharacterAnimation } from './characters/GLTFCharacter3D'

export type CharacterMachineState =
  | 'HOME'
  | 'STANDING_UP'
  | 'WALKING_TO_POI'
  | 'TALKING'
  | 'RETURNING'
  | 'SITTING_DOWN'

export type CharacterMachineEvent =
  | 'TRAVEL_REQUEST'
  | 'STAND_COMPLETE'
  | 'ARRIVE_DESTINATION'
  | 'PAUSE_COMPLETE'
  | 'ARRIVE_HOME'
  | 'SIT_COMPLETE'

export const STAND_UP_SECONDS = 0.28
export const SIT_DOWN_SECONDS = 0.45

export function transitionCharacterState(
  state: CharacterMachineState,
  event: CharacterMachineEvent,
): CharacterMachineState {
  if (state === 'HOME' && event === 'TRAVEL_REQUEST') return 'STANDING_UP'
  if (state === 'STANDING_UP' && event === 'STAND_COMPLETE') return 'WALKING_TO_POI'
  if (state === 'WALKING_TO_POI' && event === 'ARRIVE_DESTINATION') return 'TALKING'
  if (state === 'TALKING' && event === 'PAUSE_COMPLETE') return 'RETURNING'
  if (state === 'RETURNING' && event === 'ARRIVE_HOME') return 'SITTING_DOWN'
  if (state === 'SITTING_DOWN' && event === 'SIT_COMPLETE') return 'HOME'
  return state
}

export function animationForMachineState(
  state: CharacterMachineState,
): CharacterAnimation | undefined {
  if (state === 'STANDING_UP') return 'Idle'
  if (state === 'WALKING_TO_POI') return 'Walk'
  if (state === 'TALKING') return 'Talking'
  if (state === 'RETURNING') return 'Walk'
  if (state === 'SITTING_DOWN') return 'Sit'
  return undefined
}
