import type { AgentName } from '../types'
import { getVisitorPoiId } from './OfficePOI'

export interface AgentTravelRequest {
  id: number
  from: AgentName
  to: AgentName
  targetPoiId: string
  pauseSeconds: number
}

export function createHandoffTravel(
  from: AgentName,
  to: AgentName,
  id: number,
): AgentTravelRequest {
  return {
    id,
    from,
    to,
    targetPoiId: getVisitorPoiId(to),
    pauseSeconds: 1.15,
  }
}

export { getAgentCharacterHome } from './OfficePOI'
