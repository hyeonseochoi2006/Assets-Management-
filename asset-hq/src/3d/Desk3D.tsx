import type { AgentStatus } from '../types'

interface Desk3DProps {
  status: AgentStatus
}

const monitorColor: Record<AgentStatus, string> = {
  IDLE: '#334155',
  WORKING: '#f6c85f',
  DONE: '#59d39d',
  ERROR: '#ff6b6b',
}

export function Desk3D({ status }: Desk3DProps) {
  const active = status === 'WORKING'

  return (
    <group position={[0, 0, -0.15]}>
      <mesh position={[0, 0.58, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.25, 0.16, 0.9]} />
        <meshStandardMaterial color="#2b3445" roughness={0.7} />
      </mesh>
      <mesh position={[-0.88, 0.28, 0]} castShadow>
        <boxGeometry args={[0.12, 0.6, 0.12]} />
        <meshStandardMaterial color="#1a2230" />
      </mesh>
      <mesh position={[0.88, 0.28, 0]} castShadow>
        <boxGeometry args={[0.12, 0.6, 0.12]} />
        <meshStandardMaterial color="#1a2230" />
      </mesh>
      <mesh position={[0, 1.06, -0.18]} castShadow>
        <boxGeometry args={[1.05, 0.62, 0.08]} />
        <meshStandardMaterial color="#0e1522" />
      </mesh>
      <mesh position={[0, 1.06, -0.13]}>
        <boxGeometry args={[0.92, 0.49, 0.025]} />
        <meshStandardMaterial
          color={monitorColor[status]}
          emissive={monitorColor[status]}
          emissiveIntensity={active ? 1.2 : status === 'IDLE' ? 0.05 : 0.35}
        />
      </mesh>
      <mesh position={[0, 0.75, -0.18]} castShadow>
        <boxGeometry args={[0.08, 0.35, 0.08]} />
        <meshStandardMaterial color="#202939" />
      </mesh>
      <mesh position={[0, 0.68, 0.18]} castShadow>
        <boxGeometry args={[0.8, 0.05, 0.3]} />
        <meshStandardMaterial color="#111827" />
      </mesh>
    </group>
  )
}
