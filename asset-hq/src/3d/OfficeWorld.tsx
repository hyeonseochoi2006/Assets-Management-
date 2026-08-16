import { useEffect, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'

import type { AgentMap, AgentName, AgentStatus } from '../types'
import { AGENT_POSITIONS, CEO_POSITION, ROOM_SIZE, type Vec3 } from './agentPositions'
import { Agent3D } from './Agent3D'
import { CameraControls } from './CameraControls'
import { DataPacket3D } from './DataPacket3D'
import { Desk3D } from './Desk3D'
import {
  createHandoffTravel,
  type AgentTravelRequest,
} from './officeNavigation'

interface OfficeWorldProps {
  agents: AgentMap
  pipelineOrder: AgentName[]
  selectedAgent: AgentName
  onSelectAgent: (agent: AgentName) => void
}

interface Handoff {
  from: AgentName
  to: AgentName
  id: number
}

type CorridorSide = 'left' | 'right'

function SideWall({
  x,
  depth,
  hasDoor,
}: {
  x: number
  depth: number
  hasDoor: boolean
}) {
  if (!hasDoor) {
    return (
      <mesh position={[x, 0.75, 0]} receiveShadow>
        <boxGeometry args={[0.12, 1.5, depth]} />
        <meshStandardMaterial color="#141d2c" roughness={0.92} />
      </mesh>
    )
  }

  const doorGap = 1.9
  const segmentDepth = (depth - doorGap) / 2
  const segmentOffset = (doorGap + segmentDepth) / 2

  return (
    <>
      <mesh position={[x, 0.75, -segmentOffset]} receiveShadow>
        <boxGeometry args={[0.12, 1.5, segmentDepth]} />
        <meshStandardMaterial color="#141d2c" roughness={0.92} />
      </mesh>
      <mesh position={[x, 0.75, segmentOffset]} receiveShadow>
        <boxGeometry args={[0.12, 1.5, segmentDepth]} />
        <meshStandardMaterial color="#141d2c" roughness={0.92} />
      </mesh>
    </>
  )
}

function RoomShell({
  position,
  wide = false,
  corridorSide,
}: {
  position: Vec3
  wide?: boolean
  corridorSide?: CorridorSide
}) {
  const width = wide ? 8.4 : ROOM_SIZE[0]
  const depth = ROOM_SIZE[1]

  return (
    <group position={position}>
      <mesh position={[0, 0.06, 0]} receiveShadow>
        <boxGeometry args={[width, 0.12, depth]} />
        <meshStandardMaterial color="#121a28" roughness={0.9} />
      </mesh>
      <mesh position={[0, 0.75, -depth / 2]} receiveShadow>
        <boxGeometry args={[width, 1.5, 0.12]} />
        <meshStandardMaterial color="#172133" roughness={0.92} />
      </mesh>
      <SideWall x={-width / 2} depth={depth} hasDoor={corridorSide === 'left'} />
      <SideWall x={width / 2} depth={depth} hasDoor={corridorSide === 'right'} />
    </group>
  )
}

function CorridorFloor() {
  return (
    <group>
      <mesh position={[0, 0.025, 0.35]} receiveShadow>
        <boxGeometry args={[1.45, 0.05, 9.9]} />
        <meshStandardMaterial color="#101827" roughness={0.94} />
      </mesh>
      {[4.75, 1.75, -1.35].map((z) => (
        <mesh key={z} position={[0, 0.026, z]} receiveShadow>
          <boxGeometry args={[4.2, 0.052, 0.62]} />
          <meshStandardMaterial color="#111b2c" roughness={0.94} />
        </mesh>
      ))}
      <mesh position={[0, 0.026, -3.75]} receiveShadow>
        <boxGeometry args={[1.45, 0.052, 1.25]} />
        <meshStandardMaterial color="#111b2c" roughness={0.94} />
      </mesh>
    </group>
  )
}

function StaticCEO() {
  return (
    <group position={CEO_POSITION}>
      <Desk3D status="IDLE" />
      <group position={[0, 0.03, 0.78]}>
        <mesh position={[0, 1.45, 0]} castShadow>
          <sphereGeometry args={[0.27, 24, 24]} />
          <meshStandardMaterial color="#d9ae91" roughness={0.75} />
        </mesh>
        <mesh position={[0, 1.04, 0]} castShadow>
          <boxGeometry args={[0.62, 0.74, 0.38]} />
          <meshStandardMaterial color="#354f92" roughness={0.7} />
        </mesh>
        <mesh position={[0, 0.55, 0.18]} castShadow>
          <boxGeometry args={[0.68, 0.12, 0.62]} />
          <meshStandardMaterial color="#202735" />
        </mesh>
      </group>
      <mesh position={[0, 0.035, 0.1]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.78, 0.88, 40]} />
        <meshBasicMaterial color="#6f8edb" transparent opacity={0.75} />
      </mesh>
    </group>
  )
}

const statusLabel: Record<AgentStatus, string> = {
  IDLE: '대기',
  WORKING: '업무 중',
  DONE: '완료',
  ERROR: '오류',
}

export function OfficeWorld({ agents, pipelineOrder, selectedAgent, onSelectAgent }: OfficeWorldProps) {
  const previousAgents = useRef<AgentMap | null>(null)
  const handoffTimer = useRef<number | null>(null)
  const [handoff, setHandoff] = useState<Handoff | null>(null)
  const [travelRequest, setTravelRequest] = useState<AgentTravelRequest | null>(null)

  useEffect(() => {
    const previous = previousAgents.current

    for (let index = 0; index < pipelineOrder.length - 1; index += 1) {
      const from = pipelineOrder[index]
      const to = pipelineOrder[index + 1]
      const activeNow = agents[from].status === 'DONE' && agents[to].status === 'WORKING'
      const activeBefore = previous
        ? previous[from].status === 'DONE' && previous[to].status === 'WORKING'
        : false

      if (activeNow && !activeBefore) {
        const id = Date.now() + index
        if (handoffTimer.current) window.clearTimeout(handoffTimer.current)

        setTravelRequest(createHandoffTravel(from, to, id))
        setHandoff({ from, to, id })
        handoffTimer.current = window.setTimeout(() => setHandoff(null), 1500)
        break
      }
    }

    previousAgents.current = agents
  }, [agents, pipelineOrder])

  useEffect(
    () => () => {
      if (handoffTimer.current) window.clearTimeout(handoffTimer.current)
    },
    [],
  )

  return (
    <section className="three-hq-panel">
      <div className="three-hq-heading">
        <div>
          <div className="eyebrow">THREE.JS LIVE HQ</div>
          <h2>Asset Management 3D Office</h2>
        </div>
        <span>NavMesh 이동 · 드래그: 회전 · 스크롤/핀치: 확대</span>
      </div>

      <div className="three-hq-canvas">
        <Canvas shadows dpr={[1, 1.5]} camera={{ position: [12, 11, 16], fov: 42, near: 0.1, far: 100 }}>
          <color attach="background" args={['#050811']} />
          <fog attach="fog" args={['#050811', 20, 38]} />
          <ambientLight intensity={0.72} />
          <directionalLight
            castShadow
            position={[7, 13, 9]}
            intensity={1.35}
            color="#dce7ff"
            shadow-mapSize-width={1024}
            shadow-mapSize-height={1024}
          />
          <pointLight position={[-8, 6, 5]} intensity={0.8} color="#557ac9" distance={20} />

          <mesh position={[0, -0.05, 0]} receiveShadow>
            <boxGeometry args={[15.5, 0.1, 13.5]} />
            <meshStandardMaterial color="#080d16" roughness={1} />
          </mesh>
          <gridHelper args={[14, 14, '#22314b', '#101827']} position={[0, 0.015, 0]} />
          <CorridorFloor />

          <RoomShell position={CEO_POSITION} corridorSide="right" />
          <RoomShell position={AGENT_POSITIONS.CIO} corridorSide="left" />
          <RoomShell position={AGENT_POSITIONS.Analysis} corridorSide="right" />
          <RoomShell position={AGENT_POSITIONS.Portfolio} corridorSide="left" />
          <RoomShell position={AGENT_POSITIONS.Risk} corridorSide="right" />
          <RoomShell position={AGENT_POSITIONS.Execution} corridorSide="left" />
          <RoomShell position={AGENT_POSITIONS.Briefing} wide />

          <StaticCEO />
          {(Object.keys(AGENT_POSITIONS) as AgentName[]).map((agent) => (
            <Agent3D
              key={agent}
              agent={agent}
              state={agents[agent]}
              position={AGENT_POSITIONS[agent]}
              selected={selectedAgent === agent}
              travelRequest={travelRequest}
              onSelect={onSelectAgent}
            />
          ))}

          {handoff && <DataPacket3D key={handoff.id} from={handoff.from} to={handoff.to} />}
          <CameraControls />
        </Canvas>
      </div>

      <div className="three-agent-legend">
        {(Object.keys(AGENT_POSITIONS) as AgentName[]).map((agent) => (
          <button
            type="button"
            key={agent}
            className={selectedAgent === agent ? 'selected' : ''}
            onClick={() => onSelectAgent(agent)}
          >
            <i className={`guide-dot ${agents[agent].status.toLowerCase()}`} />
            <span>{agent.toUpperCase()}</span>
            <small>{statusLabel[agents[agent].status]}</small>
          </button>
        ))}
      </div>
    </section>
  )
}
