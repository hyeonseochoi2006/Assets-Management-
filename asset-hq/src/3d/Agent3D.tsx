import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Group, Mesh } from 'three'

import type { AgentName, AgentState } from '../types'
import type { Vec3 } from './agentPositions'
import { Desk3D } from './Desk3D'

interface Agent3DProps {
  agent: AgentName
  state: AgentState
  position: Vec3
  selected: boolean
  onSelect: (agent: AgentName) => void
}

const bodyColor: Record<AgentName, string> = {
  CIO: '#6f8edb',
  Analysis: '#5e9bc7',
  Portfolio: '#756fd2',
  Risk: '#d28b65',
  Execution: '#5cae8d',
  Briefing: '#a875c9',
}

export function Agent3D({ agent, state, position, selected, onSelect }: Agent3DProps) {
  const characterRef = useRef<Group>(null)
  const leftArmRef = useRef<Mesh>(null)
  const rightArmRef = useRef<Mesh>(null)

  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    const working = state.status === 'WORKING'

    if (characterRef.current) {
      characterRef.current.position.y = working ? 0.03 + Math.sin(t * 5) * 0.025 : 0.03
    }
    if (leftArmRef.current) {
      leftArmRef.current.rotation.x = working ? -0.8 + Math.sin(t * 11) * 0.22 : -0.45
    }
    if (rightArmRef.current) {
      rightArmRef.current.rotation.x = working ? -0.8 + Math.sin(t * 11 + Math.PI) * 0.22 : -0.45
    }
  })

  const statusColor =
    state.status === 'WORKING'
      ? '#f6c85f'
      : state.status === 'DONE'
        ? '#59d39d'
        : state.status === 'ERROR'
          ? '#ff6b6b'
          : '#566175'

  return (
    <group position={position} onClick={(event) => { event.stopPropagation(); onSelect(agent) }}>
      <Desk3D status={state.status} />

      <group ref={characterRef} position={[0, 0.03, 0.78]}>
        <mesh position={[0, 1.45, 0]} castShadow>
          <sphereGeometry args={[0.26, 24, 24]} />
          <meshStandardMaterial color="#d9ae91" roughness={0.75} />
        </mesh>
        <mesh position={[0, 1.58, -0.03]} castShadow>
          <sphereGeometry args={[0.265, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#202735" roughness={0.9} />
        </mesh>
        <mesh position={[0, 1.03, 0]} castShadow>
          <boxGeometry args={[0.58, 0.72, 0.36]} />
          <meshStandardMaterial color={bodyColor[agent]} roughness={0.7} />
        </mesh>
        <mesh ref={leftArmRef} position={[-0.38, 1.08, -0.03]} rotation={[-0.45, 0, 0.12]} castShadow>
          <cylinderGeometry args={[0.085, 0.085, 0.58, 12]} />
          <meshStandardMaterial color={bodyColor[agent]} />
        </mesh>
        <mesh ref={rightArmRef} position={[0.38, 1.08, -0.03]} rotation={[-0.45, 0, -0.12]} castShadow>
          <cylinderGeometry args={[0.085, 0.085, 0.58, 12]} />
          <meshStandardMaterial color={bodyColor[agent]} />
        </mesh>
        <mesh position={[0, 0.55, 0.18]} castShadow>
          <boxGeometry args={[0.65, 0.12, 0.62]} />
          <meshStandardMaterial color="#202735" />
        </mesh>
      </group>

      <mesh position={[0, 0.035, 0.1]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.72, 0.82, 40]} />
        <meshBasicMaterial color={selected ? '#8ea9ff' : statusColor} transparent opacity={selected ? 0.95 : 0.48} />
      </mesh>
      {state.status === 'WORKING' && (
        <pointLight position={[0, 2.1, 0]} color="#f6c85f" intensity={1.1} distance={4.2} />
      )}
      {state.status === 'ERROR' && (
        <pointLight position={[0, 2.1, 0]} color="#ff5f66" intensity={1.3} distance={4.2} />
      )}
    </group>
  )
}
