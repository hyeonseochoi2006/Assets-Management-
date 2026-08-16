import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Group, Mesh } from 'three'

import type { AgentName, AgentStatus } from '../../types'
import { getCharacterPose } from './characterMotion'
import { CHARACTER_PROFILES, type CharacterProfile } from './characterProfiles'

interface CharacterModel3DProps {
  agent: AgentName
  status: AgentStatus
}

function Hair({ profile }: { profile: CharacterProfile }) {
  const common = <meshStandardMaterial color={profile.hair} roughness={0.92} flatShading />

  return (
    <group>
      <mesh position={[0, 1.67, 0.02]} scale={[1.04, 0.7, 1.02]} castShadow>
        <icosahedronGeometry args={[0.34, 1]} />
        {common}
      </mesh>

      {profile.hairStyle === 'side' && (
        <mesh position={[0.15, 1.7, -0.18]} rotation={[0.05, 0, -0.35]} castShadow>
          <boxGeometry args={[0.34, 0.12, 0.26]} />
          <meshStandardMaterial color={profile.hair} roughness={0.92} flatShading />
        </mesh>
      )}

      {profile.hairStyle === 'crop' && (
        <mesh position={[0, 1.73, -0.06]} scale={[0.92, 0.55, 0.9]} castShadow>
          <icosahedronGeometry args={[0.29, 1]} />
          <meshStandardMaterial color={profile.hair} roughness={0.95} flatShading />
        </mesh>
      )}

      {profile.hairStyle === 'bob' && (
        <>
          <mesh position={[-0.29, 1.46, 0]} castShadow>
            <boxGeometry args={[0.12, 0.42, 0.32]} />
            <meshStandardMaterial color={profile.hair} roughness={0.92} flatShading />
          </mesh>
          <mesh position={[0.29, 1.46, 0]} castShadow>
            <boxGeometry args={[0.12, 0.42, 0.32]} />
            <meshStandardMaterial color={profile.hair} roughness={0.92} flatShading />
          </mesh>
        </>
      )}

      {profile.hairStyle === 'swept' && (
        <mesh position={[-0.1, 1.74, -0.16]} rotation={[0.1, 0.1, 0.45]} castShadow>
          <boxGeometry args={[0.4, 0.13, 0.26]} />
          <meshStandardMaterial color={profile.hair} roughness={0.92} flatShading />
        </mesh>
      )}

      {profile.hairStyle === 'short' && (
        <mesh position={[0, 1.73, -0.08]} scale={[0.96, 0.52, 0.9]} castShadow>
          <dodecahedronGeometry args={[0.3, 0]} />
          <meshStandardMaterial color={profile.hair} roughness={0.94} flatShading />
        </mesh>
      )}

      {profile.hairStyle === 'wave' && (
        <>
          <mesh position={[-0.23, 1.61, -0.02]} rotation={[0, 0, 0.25]} castShadow>
            <icosahedronGeometry args={[0.18, 1]} />
            <meshStandardMaterial color={profile.hair} roughness={0.92} flatShading />
          </mesh>
          <mesh position={[0.23, 1.61, -0.02]} rotation={[0, 0, -0.25]} castShadow>
            <icosahedronGeometry args={[0.18, 1]} />
            <meshStandardMaterial color={profile.hair} roughness={0.92} flatShading />
          </mesh>
        </>
      )}
    </group>
  )
}

export function CharacterModel3D({ agent, status }: CharacterModel3DProps) {
  const profile = CHARACTER_PROFILES[agent]
  const rootRef = useRef<Group>(null)
  const torsoRef = useRef<Group>(null)
  const headRef = useRef<Group>(null)
  const leftArmRef = useRef<Mesh>(null)
  const rightArmRef = useRef<Mesh>(null)
  const leftLegRef = useRef<Mesh>(null)
  const rightLegRef = useRef<Mesh>(null)

  useFrame(({ clock }) => {
    const pose = getCharacterPose(status, clock.elapsedTime)

    if (rootRef.current) rootRef.current.position.y = pose.bodyY
    if (torsoRef.current) torsoRef.current.rotation.x = pose.bodyTilt
    if (headRef.current) headRef.current.rotation.y = pose.headTurn

    if (leftArmRef.current) {
      leftArmRef.current.rotation.x = pose.leftArmX
      leftArmRef.current.rotation.z = pose.leftArmZ
    }
    if (rightArmRef.current) {
      rightArmRef.current.rotation.x = pose.rightArmX
      rightArmRef.current.rotation.z = pose.rightArmZ
    }
    if (leftLegRef.current) leftLegRef.current.rotation.x = pose.leftLegX
    if (rightLegRef.current) rightLegRef.current.rotation.x = pose.rightLegX
  })

  return (
    <group ref={rootRef} position={[0, 0.02, 0]}>
      <group ref={torsoRef}>
        <group ref={headRef}>
          <mesh position={[0, 1.48, 0]} castShadow>
            <icosahedronGeometry args={[0.34, 2]} />
            <meshStandardMaterial color={profile.skin} roughness={0.82} flatShading />
          </mesh>

          <Hair profile={profile} />

          <mesh position={[-0.115, 1.5, -0.3]} castShadow>
            <sphereGeometry args={[0.035, 8, 8]} />
            <meshStandardMaterial color="#151820" roughness={0.8} />
          </mesh>
          <mesh position={[0.115, 1.5, -0.3]} castShadow>
            <sphereGeometry args={[0.035, 8, 8]} />
            <meshStandardMaterial color="#151820" roughness={0.8} />
          </mesh>
          <mesh position={[0, 1.39, -0.315]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.07, 0.012, 6, 12, Math.PI]} />
            <meshStandardMaterial color="#704c45" roughness={0.85} />
          </mesh>
        </group>

        <mesh position={[0, 1.02, 0]} castShadow>
          <cylinderGeometry args={[0.27, 0.34, 0.66, 6]} />
          <meshStandardMaterial color={profile.jacket} roughness={0.78} flatShading />
        </mesh>
        <mesh position={[0, 1.14, -0.29]} rotation={[0.08, 0, 0]} castShadow>
          <boxGeometry args={[0.2, 0.26, 0.035]} />
          <meshStandardMaterial color={profile.shirt} roughness={0.75} />
        </mesh>
        <mesh position={[0, 1.09, -0.315]} castShadow>
          <boxGeometry args={[0.045, 0.19, 0.025]} />
          <meshStandardMaterial color={profile.accent} roughness={0.72} />
        </mesh>

        <mesh ref={leftArmRef} position={[-0.35, 1.05, -0.02]} rotation={[-0.35, 0, 0.12]} castShadow>
          <cylinderGeometry args={[0.085, 0.095, 0.58, 8]} />
          <meshStandardMaterial color={profile.jacket} roughness={0.8} flatShading />
        </mesh>
        <mesh ref={rightArmRef} position={[0.35, 1.05, -0.02]} rotation={[-0.35, 0, -0.12]} castShadow>
          <cylinderGeometry args={[0.085, 0.095, 0.58, 8]} />
          <meshStandardMaterial color={profile.jacket} roughness={0.8} flatShading />
        </mesh>

        <mesh ref={leftLegRef} position={[-0.16, 0.55, 0.08]} castShadow>
          <cylinderGeometry args={[0.1, 0.11, 0.5, 7]} />
          <meshStandardMaterial color={profile.trousers} roughness={0.88} flatShading />
        </mesh>
        <mesh ref={rightLegRef} position={[0.16, 0.55, 0.08]} castShadow>
          <cylinderGeometry args={[0.1, 0.11, 0.5, 7]} />
          <meshStandardMaterial color={profile.trousers} roughness={0.88} flatShading />
        </mesh>

        <mesh position={[-0.16, 0.28, -0.03]} castShadow>
          <boxGeometry args={[0.2, 0.12, 0.34]} />
          <meshStandardMaterial color={profile.shoes} roughness={0.9} flatShading />
        </mesh>
        <mesh position={[0.16, 0.28, -0.03]} castShadow>
          <boxGeometry args={[0.2, 0.12, 0.34]} />
          <meshStandardMaterial color={profile.shoes} roughness={0.9} flatShading />
        </mesh>
      </group>
    </group>
  )
}
