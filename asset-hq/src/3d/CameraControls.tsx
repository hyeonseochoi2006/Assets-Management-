import { useEffect, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

export function CameraControls() {
  const { camera, gl } = useThree()
  const controlsRef = useRef<OrbitControls | null>(null)

  useEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.minDistance = 10
    controls.maxDistance = 28
    controls.maxPolarAngle = Math.PI / 2.08
    controls.target.set(0, 0.4, 0)
    controls.update()
    controlsRef.current = controls

    return () => controls.dispose()
  }, [camera, gl])

  useFrame(() => controlsRef.current?.update())
  return null
}
