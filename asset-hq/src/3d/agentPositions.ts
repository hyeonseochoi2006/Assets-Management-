import type { AgentName } from '../types'

export type Vec3 = [number, number, number]

export const AGENT_POSITIONS: Record<AgentName, Vec3> = {
  CIO: [4.2, 0, 4.1],
  Analysis: [-4.2, 0, 1.1],
  Portfolio: [4.2, 0, 1.1],
  Risk: [-4.2, 0, -2.0],
  Execution: [4.2, 0, -2.0],
  Briefing: [0, 0, -5.0],
}

export const CEO_POSITION: Vec3 = [-4.2, 0, 4.1]

export const ROOM_SIZE: [number, number] = [5.8, 2.5]
