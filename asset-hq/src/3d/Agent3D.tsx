import type { AgentName, AgentState } from '../types'
import type { Vec3 } from './agentPositions'
import { GLTFCharacter3D } from './characters/GLTFCharacter3D'
import { Desk3D } from './Desk3D'

interface Agent3DProps {
  agent: AgentName
  state: AgentState
  position: Vec3
  selected: boolean
  onSelect: (agent: AgentName) => void
}

export function Agent3D({ agent, state, position, selected, onSelect }: Agent3DProps) {
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
      <group position={[0, 0, 0.78]}>
        <GLTFCharacter3D agent={agent} status={state.status} />
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
