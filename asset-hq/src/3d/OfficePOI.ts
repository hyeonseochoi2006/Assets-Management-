import type { AgentName } from '../types'
import { AGENT_POSITIONS, type Vec3 } from './agentPositions'

export type OfficePoiKind = 'DESK' | 'VISITOR' | 'CORRIDOR'

export interface OfficePoi {
  id: string
  label: string
  kind: OfficePoiKind
  position: Vec3
  agent?: AgentName
}

const CHARACTER_HOME_Z_OFFSET = 0.78

export function getAgentCharacterHome(agent: AgentName): Vec3 {
  const [x, y, z] = AGENT_POSITIONS[agent]
  return [x, y, z + CHARACTER_HOME_Z_OFFSET]
}

function getVisitorPosition(agent: AgentName): Vec3 {
  const [x, y, z] = AGENT_POSITIONS[agent]

  if (agent === 'Briefing') {
    return [0.55, y, -3.95]
  }

  const visitorX = x < 0 ? -3.25 : 3.25
  return [visitorX, y, z + 0.72]
}

const DESK_POI_IDS: Record<AgentName, string> = {
  CIO: 'DESK_CIO',
  Analysis: 'DESK_ANALYSIS',
  Portfolio: 'DESK_PORTFOLIO',
  Risk: 'DESK_RISK',
  Execution: 'DESK_EXECUTION',
  Briefing: 'DESK_BRIEFING',
}

const VISITOR_POI_IDS: Record<AgentName, string> = {
  CIO: 'VISITOR_CIO',
  Analysis: 'VISITOR_ANALYSIS',
  Portfolio: 'VISITOR_PORTFOLIO',
  Risk: 'VISITOR_RISK',
  Execution: 'VISITOR_EXECUTION',
  Briefing: 'VISITOR_BRIEFING',
}

export const OFFICE_POIS: Record<string, OfficePoi> = {
  CORRIDOR_CENTER: {
    id: 'CORRIDOR_CENTER',
    label: 'Central Corridor',
    kind: 'CORRIDOR',
    position: [0, 0, 0.45],
  },
  BRIEFING_ENTRY: {
    id: 'BRIEFING_ENTRY',
    label: 'Briefing Entry',
    kind: 'CORRIDOR',
    position: [0, 0, -3.65],
  },
}

for (const agent of Object.keys(AGENT_POSITIONS) as AgentName[]) {
  const deskId = DESK_POI_IDS[agent]
  const visitorId = VISITOR_POI_IDS[agent]

  OFFICE_POIS[deskId] = {
    id: deskId,
    label: `${agent} Desk`,
    kind: 'DESK',
    position: getAgentCharacterHome(agent),
    agent,
  }

  OFFICE_POIS[visitorId] = {
    id: visitorId,
    label: `${agent} Visitor Spot`,
    kind: 'VISITOR',
    position: getVisitorPosition(agent),
    agent,
  }
}

export function getDeskPoiId(agent: AgentName): string {
  return DESK_POI_IDS[agent]
}

export function getVisitorPoiId(agent: AgentName): string {
  return VISITOR_POI_IDS[agent]
}

export function getOfficePoi(id: string): OfficePoi {
  const poi = OFFICE_POIS[id]
  if (!poi) throw new Error(`Unknown office POI: ${id}`)
  return poi
}

export function getOfficePoiPosition(id: string): Vec3 {
  const [x, y, z] = getOfficePoi(id).position
  return [x, y, z]
}
