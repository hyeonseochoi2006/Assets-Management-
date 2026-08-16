import type { AgentName } from '../types'
import { AGENT_POSITIONS, type Vec3 } from './agentPositions'

export interface AgentTravelRequest {
  id: number
  from: AgentName
  to: AgentName
  route: Vec3[]
  pauseSeconds: number
}

const CHARACTER_HOME_Z_OFFSET = 0.78
const DOOR_Z_OFFSET = 0.2
const INNER_DOOR_OFFSET_X = 2.55
const VISITOR_OFFSET_X = 1.55
const CORRIDOR_EDGE_X = 0.62
const BRIEFING_DOOR_Z = -3.55
const BRIEFING_VISITOR_Z = -4.05

export function getAgentCharacterHome(agent: AgentName): Vec3 {
  const [x, y, z] = AGENT_POSITIONS[agent]
  return [x, y, z + CHARACTER_HOME_Z_OFFSET]
}

function towardCorridor(x: number): -1 | 1 {
  return x < 0 ? 1 : -1
}

function corridorSideX(x: number): number {
  return x < 0 ? -CORRIDOR_EDGE_X : CORRIDOR_EDGE_X
}

function exitRoom(agent: AgentName): Vec3[] {
  const [x, y, z] = AGENT_POSITIONS[agent]

  if (agent === 'Briefing') {
    return [
      [0, y, BRIEFING_VISITOR_Z],
      [0, y, BRIEFING_DOOR_Z],
    ]
  }

  const direction = towardCorridor(x)
  const doorZ = z + DOOR_Z_OFFSET

  return [
    [x + direction * INNER_DOOR_OFFSET_X, y, doorZ],
    [corridorSideX(x), y, doorZ],
    [0, y, doorZ],
  ]
}

function enterRoom(agent: AgentName): Vec3[] {
  const [x, y, z] = AGENT_POSITIONS[agent]

  if (agent === 'Briefing') {
    return [
      [0, y, BRIEFING_DOOR_Z],
      [0, y, BRIEFING_VISITOR_Z],
    ]
  }

  const direction = towardCorridor(x)
  const doorZ = z + DOOR_Z_OFFSET

  return [
    [0, y, doorZ],
    [corridorSideX(x), y, doorZ],
    [x + direction * INNER_DOOR_OFFSET_X, y, doorZ],
    [x + direction * VISITOR_OFFSET_X, y, z + 0.58],
  ]
}

export function buildHandoffRoute(from: AgentName, to: AgentName): Vec3[] {
  const fromExit = exitRoom(from)
  const toEntry = enterRoom(to)
  const targetZ = to === 'Briefing' ? BRIEFING_DOOR_Z : AGENT_POSITIONS[to][2] + DOOR_Z_OFFSET

  const route: Vec3[] = [...fromExit]
  const lastExit = route[route.length - 1]

  if (Math.abs(lastExit[2] - targetZ) > 0.05) {
    route.push([0, 0, targetZ])
  }

  for (const point of toEntry) {
    const previous = route[route.length - 1]
    if (
      !previous ||
      Math.abs(previous[0] - point[0]) > 0.01 ||
      Math.abs(previous[2] - point[2]) > 0.01
    ) {
      route.push(point)
    }
  }

  return route
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
    route: buildHandoffRoute(from, to),
    pauseSeconds: 1.15,
  }
}
