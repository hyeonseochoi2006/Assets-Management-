import { useEffect, useMemo } from 'react'
import { useFrame, useLoader } from '@react-three/fiber'
import {
  AnimationClip,
  AnimationMixer,
  LoopOnce,
  LoopRepeat,
  Mesh,
} from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import type { AgentName, AgentStatus } from '../../types'

interface GLTFCharacter3DProps {
  agent: AgentName
  status: AgentStatus
}

const STATUS_CLIP: Record<AgentStatus, string> = {
  IDLE: 'Sit',
  WORKING: 'Typing',
  DONE: 'Talking',
  ERROR: 'Talking',
}

export function GLTFCharacter3D({ agent, status }: GLTFCharacter3DProps) {
  const fileName = `${agent.toLowerCase()}.glb`
  const gltf = useLoader(GLTFLoader, `/models/characters/${fileName}`)

  const scene = useMemo(() => {
    const cloned = gltf.scene.clone(true)
    cloned.traverse((object) => {
      if (object instanceof Mesh) {
        object.castShadow = true
        object.receiveShadow = true
      }
    })
    return cloned
  }, [gltf.scene])

  const mixer = useMemo(() => new AnimationMixer(scene), [scene])

  useFrame((_, delta) => {
    mixer.update(delta)
  })

  useEffect(() => {
    const clipName = STATUS_CLIP[status]
    const clip = AnimationClip.findByName(gltf.animations, clipName)
    if (!clip) return

    mixer.stopAllAction()
    const action = mixer.clipAction(clip, scene)
    action.reset()
    action.enabled = true
    action.setEffectiveWeight(1)

    if (clipName === 'Sit') {
      action.setLoop(LoopOnce, 1)
      action.clampWhenFinished = true
    } else {
      action.setLoop(LoopRepeat, Infinity)
    }

    action.fadeIn(0.18).play()

    return () => {
      action.fadeOut(0.12)
    }
  }, [gltf.animations, mixer, scene, status])

  useEffect(
    () => () => {
      mixer.stopAllAction()
      mixer.uncacheRoot(scene)
    },
    [mixer, scene],
  )

  return <primitive object={scene} />
}
