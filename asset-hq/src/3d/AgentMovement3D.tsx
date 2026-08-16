import { useEffect, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Group } from 'three'

import type { AgentName, AgentState } from '../types'
import type { Vec3 } from './agentPositions'
import {
  animationForMachineState,
  SIT_DOWN_SECONDS,
  STAND_UP_SECONDS,
  transitionCharacterState,
  type CharacterMachineEvent,
  type CharacterMachineState,
} from './CharacterStateMachine'
import {
  GLTFCharacter3D,
  type CharacterAnimation,
} from './characters/GLTFCharacter3D'
import { findOfficePath } from './OfficeNavMesh'
import { getOfficePoiPosition } from './OfficePOI'
import type { AgentTravelRequest } from './officeNavigation'

interface AgentMovement3DProps {
  agent: AgentName
  state: AgentState
  home: Vec3
  travelRequest: AgentTravelRequest | null
  onSelect: (agent: AgentName) => void
}

const WALK_SPEED = 2.35
const ARRIVAL_DISTANCE = 0.055

export function AgentMovement3D({
  agent,
  state,
  home,
  travelRequest,
  onSelect,
}: AgentMovement3DProps) {
  const groupRef = useRef<Group>(null)
  const machineStateRef = useRef<CharacterMachineState>('HOME')
  const stateElapsedRef = useRef(0)
  const activeTravelIdRef = useRef<number | null>(null)
  const activeTravelRef = useRef<AgentTravelRequest | null>(null)
  const routeRef = useRef<Vec3[]>([])
  const routeIndexRef = useRef(0)
  const [animation, setAnimation] = useState<CharacterAnimation | undefined>(undefined)

  const dispatchMachineEvent = (event: CharacterMachineEvent) => {
    const current = machineStateRef.current
    const next = transitionCharacterState(current, event)
    if (next === current) return current

    machineStateRef.current = next
    stateElapsedRef.current = 0
    setAnimation(animationForMachineState(next))
    return next
  }

  useEffect(() => {
    if (!groupRef.current || machineStateRef.current !== 'HOME') return
    groupRef.current.position.set(home[0], home[1], home[2])
    groupRef.current.rotation.y = 0
  }, [home])

  useEffect(() => {
    if (!travelRequest || travelRequest.from !== agent) return
    if (activeTravelIdRef.current === travelRequest.id) return
    if (machineStateRef.current !== 'HOME') return

    activeTravelIdRef.current = travelRequest.id
    activeTravelRef.current = travelRequest
    routeRef.current = []
    routeIndexRef.current = 0
    dispatchMachineEvent('TRAVEL_REQUEST')
  }, [agent, travelRequest])

  useFrame((_, delta) => {
    const group = groupRef.current
    if (!group) return

    stateElapsedRef.current += delta
    const machineState = machineStateRef.current

    if (machineState === 'STANDING_UP') {
      if (stateElapsedRef.current >= STAND_UP_SECONDS) {
        const request = activeTravelRef.current
        if (!request) {
          machineStateRef.current = 'HOME'
          setAnimation(undefined)
          return
        }

        const target = getOfficePoiPosition(request.targetPoiId)
        const start: Vec3 = [group.position.x, group.position.y, group.position.z]
        routeRef.current = findOfficePath(start, target)
        routeIndexRef.current = 0
        dispatchMachineEvent('STAND_COMPLETE')
      }
      return
    }

    if (machineState === 'TALKING') {
      const pauseSeconds = activeTravelRef.current?.pauseSeconds ?? 1.15
      if (stateElapsedRef.current >= pauseSeconds) {
        const start: Vec3 = [group.position.x, group.position.y, group.position.z]
        routeRef.current = findOfficePath(start, home)
        routeIndexRef.current = 0
        dispatchMachineEvent('PAUSE_COMPLETE')
      }
      return
    }

    if (machineState === 'SITTING_DOWN') {
      if (stateElapsedRef.current >= SIT_DOWN_SECONDS) {
        group.position.set(home[0], home[1], home[2])
        group.rotation.y = 0
        activeTravelRef.current = null
        routeRef.current = []
        routeIndexRef.current = 0
        dispatchMachineEvent('SIT_COMPLETE')
      }
      return
    }

    if (machineState !== 'WALKING_TO_POI' && machineState !== 'RETURNING') return

    const target = routeRef.current[routeIndexRef.current]
    if (!target) {
      if (machineState === 'WALKING_TO_POI') {
        dispatchMachineEvent('ARRIVE_DESTINATION')
      } else {
        group.position.set(home[0], home[1], home[2])
        group.rotation.y = 0
        dispatchMachineEvent('ARRIVE_HOME')
      }
      return
    }

    const dx = target[0] - group.position.x
    const dy = target[1] - group.position.y
    const dz = target[2] - group.position.z
    const distance = Math.sqrt(dx * dx + dy * dy + dz * dz)

    if (distance <= ARRIVAL_DISTANCE) {
      group.position.set(target[0], target[1], target[2])
      routeIndexRef.current += 1
      return
    }

    const step = Math.min(WALK_SPEED * delta, distance)
    group.position.x += (dx / distance) * step
    group.position.y += (dy / distance) * step
    group.position.z += (dz / distance) * step

    if (Math.abs(dx) + Math.abs(dz) > 0.001) {
      const targetYaw = Math.atan2(-dx, -dz)
      const yawDelta = Math.atan2(
        Math.sin(targetYaw - group.rotation.y),
        Math.cos(targetYaw - group.rotation.y),
      )
      group.rotation.y += yawDelta * Math.min(1, delta * 9)
    }
  })

  return (
    <group
      ref={groupRef}
      position={home}
      onClick={(event) => {
        event.stopPropagation()
        onSelect(agent)
      }}
    >
      <GLTFCharacter3D agent={agent} status={state.status} animation={animation} />
    </group>
  )
}
