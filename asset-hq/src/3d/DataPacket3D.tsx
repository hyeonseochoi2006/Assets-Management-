import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Mesh } from 'three'

import type { AgentName } from '../types'
import { AGENT_POSITIONS } from './agentPositions'

interface DataPacket3DProps {
  from: AgentName
  to: AgentName
}

export function DataPacket3D({ from, to }: DataPacket3DProps) {
  const meshRef = useRef<Mesh>(null)
  const startRef = useRef<number | null>(null)
  const fromPosition = AGENT_POSITIONS[from]
  const toPosition = AGENT_POSITIONS[to]

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    if (startRef.current === null) startRef.current = clock.elapsedTime

    const elapsed = clock.elapsedTime - startRef.current
    const progress = Math.min(elapsed / 1.35, 1)
    const eased = progress * progress * (3 - 2 * progress)

    meshRef.current.position.x = fromPosition[0] + (toPosition[0] - fromPosition[0]) * eased
    meshRef.current.position.z = fromPosition[2] + (toPosition[2] - fromPosition[2]) * eased
    meshRef.current.position.y = 1.75 + Math.sin(progress * Math.PI) * 1.0
    meshRef.current.rotation.x += 0.05
    meshRef.current.rotation.y += 0.08
  })

  return (
    <mesh ref={meshRef} position={[fromPosition[0], 1.75, fromPosition[2]]}>
      <octahedronGeometry args={[0.22, 0]} />
      <meshStandardMaterial color="#79a8ff" emissive="#79a8ff" emissiveIntensity={2.2} />
      <pointLight color="#79a8ff" intensity={1.4} distance={3.5} />
    </mesh>
  )
}
