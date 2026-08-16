import { Shape, ShapeGeometry, Vector2, Vector3 } from 'three'
import { Pathfinding } from 'three-pathfinding'

import type { Vec3 } from './agentPositions'

const OFFICE_ZONE = 'asset-hq-office'

// Walkable floor outline. The three horizontal bars run in front of the desks,
// while the narrow vertical stem is the central corridor.
const WALKABLE_OUTLINE: Array<[number, number]> = [
  [-0.72, 5.2],
  [0.72, 5.2],
  [0.72, 5.02],
  [4.55, 5.02],
  [4.55, 4.48],
  [0.72, 4.48],
  [0.72, 2.02],
  [4.55, 2.02],
  [4.55, 1.48],
  [0.72, 1.48],
  [0.72, -1.08],
  [4.55, -1.08],
  [4.55, -1.62],
  [0.72, -1.62],
  [0.72, -4.6],
  [-0.72, -4.6],
  [-0.72, -1.62],
  [-4.55, -1.62],
  [-4.55, -1.08],
  [-0.72, -1.08],
  [-0.72, 1.48],
  [-4.55, 1.48],
  [-4.55, 2.02],
  [-0.72, 2.02],
  [-0.72, 4.48],
  [-4.55, 4.48],
  [-4.55, 5.02],
  [-0.72, 5.02],
]

export function createOfficeNavGeometry(): ShapeGeometry {
  // ShapeGeometry is created in XY. Store -Z as shape Y, then rotate the
  // finished geometry so its surface lies flat in the Three.js XZ plane.
  const points = WALKABLE_OUTLINE.map(([x, z]) => new Vector2(x, -z))
  const shape = new Shape(points)
  const geometry = new ShapeGeometry(shape)
  geometry.rotateX(-Math.PI / 2)
  geometry.computeBoundingBox()
  return geometry
}

const navGeometry = createOfficeNavGeometry()
const pathfinder = new Pathfinding()
pathfinder.setZoneData(OFFICE_ZONE, Pathfinding.createZone(navGeometry))

function toVector3([x, y, z]: Vec3): Vector3 {
  return new Vector3(x, y, z)
}

function toVec3(point: Vector3): Vec3 {
  return [point.x, point.y, point.z]
}

export function findOfficePath(start: Vec3, target: Vec3): Vec3[] {
  const startVector = toVector3(start)
  const targetVector = toVector3(target)
  const groupId = pathfinder.getGroup(OFFICE_ZONE, startVector)

  if (groupId === null || groupId === undefined) {
    return [target]
  }

  const path = pathfinder.findPath(startVector, targetVector, OFFICE_ZONE, groupId)
  if (!path || path.length === 0) {
    return [target]
  }

  return path.map(toVec3)
}

export function getOfficeNavGeometry(): ShapeGeometry {
  return navGeometry.clone()
}
