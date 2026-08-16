import { useEffect, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Group } from 'three'

import type { AgentName, AgentState } from '../types'
import type { Vec3 } from './agentPositions'
import type { AgentTravelRequest } from './officeNavigation'
import {
  GLTFCharacter3D,
  type CharacterAnimation,
} from './characters/GLTFCharacter3D'

interface AgentMovement3DProps {
  agent: AgentName
  state: AgentState
  home: Vec3
  travelRequest: AgentTravelRequest | null
  onSelect: (agent: AgentName) => void
}

type TravelPhase = 'HOME' | 'OUTBOUND' | 'PAUSE' | 'RETURNING'

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
  const phaseRef = useRef<TravelPhase>('HOME')
  const activeTravelIdRef = useRef<number | null>(null)
  const routeRef = useRef<Vec3[]>([])
  const routeIndexRef = useRef(0)
  const pauseUntilRef = useRef(0)
  const [animation, setAnimation] = useState<CharacterAnimation | undefined>(undefined)

  useEffect(() => {
    if (!groupRef.current || phaseRef.current !== 'HOME') return
    groupRef.current.position.set(home[0], home[1], home[2])
  }, [home])

  useEffect(() => {
    if (!travelRequest || travelRequest.from !== agent) return
    if (activeTravelIdRef.current === travelRequest.id) return

    activeTravelIdRef.current = travelRequest.id
    routeRef.current = [...travelRequest.route]
    routeIndexRef.current = 0
    phaseRef.current = 'OUTBOUND'
    setAnimation('Walk')
  }, [agent, travelRequest])

  useFrame(({ clock }, delta) => {
    const group = groupRef.current
    if (!group) return

    const phase = phaseRef.current

    if (phase === 'PAUSE') {
      if (clock.elapsedTime >= pauseUntilRef.current) {
        const outbound = travelRequest?.from === agent ? travelRequest.route : routeRef.current
        routeRef.current = [...outbound].slice(0, -1).reverse()
        routeRef.current.push(home)
        routeIndexRef.current = 0
        phaseRef.current = 'RETURNING'
        setAnimation('Walk')
      }
      return
    }

    if (phase !== 'OUTBOUND' && phase !== 'RETURNING') return

    const target = routeRef.current[routeIndexRef.current]
    if (!target) {
      if (phase === 'OUTBOUND') {
        phaseRef.current = 'PAUSE'
        pauseUntilRef.current = clock.elapsedTime + (travelRequest?.pauseSeconds ?? 1.15)
        setAnimation('Talking')
      } else {
        phaseRef.current = 'HOME'
        group.position.set(home[0], home[1], home[2])
        setAnimation(undefined)
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
