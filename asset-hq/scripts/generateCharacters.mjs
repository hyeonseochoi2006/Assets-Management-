import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import * as THREE from 'three'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const profilesPath = path.join(projectRoot, 'character-profiles.json')
const outputDir = path.join(projectRoot, 'public', 'models', 'characters')

const profiles = JSON.parse(await fs.readFile(profilesPath, 'utf8'))

const COMPONENT_FLOAT = 5126
const ARRAY_BUFFER = 34962

function align4(value) {
  return (value + 3) & ~3
}

function colorFactor(hex) {
  const color = new THREE.Color(hex)
  return [color.r, color.g, color.b, 1]
}

function toQuaternion(x = 0, y = 0, z = 0) {
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z))
  return [q.x, q.y, q.z, q.w]
}

function minMax(array, itemSize) {
  const min = Array(itemSize).fill(Number.POSITIVE_INFINITY)
  const max = Array(itemSize).fill(Number.NEGATIVE_INFINITY)
  for (let i = 0; i < array.length; i += itemSize) {
    for (let axis = 0; axis < itemSize; axis += 1) {
      const value = array[i + axis]
      min[axis] = Math.min(min[axis], value)
      max[axis] = Math.max(max[axis], value)
    }
  }
  return { min, max }
}

class GlbBuilder {
  constructor() {
    this.json = {
      asset: { version: '2.0', generator: 'Asset Management HQ Character Generator' },
      scene: 0,
      scenes: [{ nodes: [] }],
      nodes: [],
      meshes: [],
      materials: [],
      accessors: [],
      bufferViews: [],
      animations: [],
    }
    this.binaryChunks = []
    this.binaryLength = 0
  }

  addMaterial(name, hex, roughness = 0.8) {
    const index = this.json.materials.length
    this.json.materials.push({
      name,
      pbrMetallicRoughness: {
        baseColorFactor: colorFactor(hex),
        metallicFactor: 0,
        roughnessFactor: roughness,
      },
    })
    return index
  }

  appendBinary(typedArray, target) {
    const alignedOffset = align4(this.binaryLength)
    if (alignedOffset > this.binaryLength) {
      this.binaryChunks.push(Buffer.alloc(alignedOffset - this.binaryLength))
      this.binaryLength = alignedOffset
    }

    const source = Buffer.from(
      typedArray.buffer,
      typedArray.byteOffset,
      typedArray.byteLength,
    )
    const byteOffset = this.binaryLength
    this.binaryChunks.push(source)
    this.binaryLength += source.byteLength

    const view = {
      buffer: 0,
      byteOffset,
      byteLength: source.byteLength,
    }
    if (target) view.target = target

    const index = this.json.bufferViews.length
    this.json.bufferViews.push(view)
    return index
  }

  addFloatAccessor(values, type, itemSize, options = {}) {
    const array = values instanceof Float32Array ? values : new Float32Array(values)
    const viewIndex = this.appendBinary(array, options.target)
    const accessor = {
      bufferView: viewIndex,
      byteOffset: 0,
      componentType: COMPONENT_FLOAT,
      count: array.length / itemSize,
      type,
    }
    if (options.includeBounds) {
      const bounds = minMax(array, itemSize)
      accessor.min = bounds.min
      accessor.max = bounds.max
    }
    const index = this.json.accessors.length
    this.json.accessors.push(accessor)
    return index
  }

  addGeometry(geometry, materialIndex, name) {
    const source = geometry.index ? geometry.toNonIndexed() : geometry.clone()
    source.computeVertexNormals()

    const position = source.getAttribute('position')
    const normal = source.getAttribute('normal')

    const positions = new Float32Array(position.array)
    const normals = new Float32Array(normal.array)

    const positionAccessor = this.addFloatAccessor(positions, 'VEC3', 3, {
      target: ARRAY_BUFFER,
      includeBounds: true,
    })
    const normalAccessor = this.addFloatAccessor(normals, 'VEC3', 3, {
      target: ARRAY_BUFFER,
    })

    const meshIndex = this.json.meshes.length
    this.json.meshes.push({
      name,
      primitives: [
        {
          attributes: {
            POSITION: positionAccessor,
            NORMAL: normalAccessor,
          },
          material: materialIndex,
          mode: 4,
        },
      ],
    })

    source.dispose()
    geometry.dispose()
    return meshIndex
  }

  addNode({ name, mesh, translation, rotation, scale, children }) {
    const node = { name }
    if (mesh !== undefined) node.mesh = mesh
    if (translation) node.translation = translation
    if (rotation) node.rotation = rotation
    if (scale) node.scale = scale
    if (children?.length) node.children = children
    const index = this.json.nodes.length
    this.json.nodes.push(node)
    return index
  }

  addAnimation(name, tracks) {
    const animation = { name, samplers: [], channels: [] }

    for (const track of tracks) {
      const inputAccessor = this.addFloatAccessor(track.times, 'SCALAR', 1, {
        includeBounds: true,
      })
      const itemSize = track.path === 'rotation' ? 4 : 3
      const outputAccessor = this.addFloatAccessor(
        track.values,
        track.path === 'rotation' ? 'VEC4' : 'VEC3',
        itemSize,
      )
      const samplerIndex = animation.samplers.length
      animation.samplers.push({
        input: inputAccessor,
        output: outputAccessor,
        interpolation: 'LINEAR',
      })
      animation.channels.push({
        sampler: samplerIndex,
        target: {
          node: track.node,
          path: track.path,
        },
      })
    }

    this.json.animations.push(animation)
  }

  finish(sceneRootNode) {
    this.json.scenes[0].nodes = [sceneRootNode]
    this.json.buffers = [{ byteLength: align4(this.binaryLength) }]

    const binary = Buffer.concat([
      ...this.binaryChunks,
      Buffer.alloc(align4(this.binaryLength) - this.binaryLength),
    ])

    const jsonBufferRaw = Buffer.from(JSON.stringify(this.json), 'utf8')
    const jsonPaddedLength = align4(jsonBufferRaw.length)
    const jsonBuffer = Buffer.concat([
      jsonBufferRaw,
      Buffer.alloc(jsonPaddedLength - jsonBufferRaw.length, 0x20),
    ])

    const totalLength = 12 + 8 + jsonBuffer.length + 8 + binary.length
    const header = Buffer.alloc(12)
    header.writeUInt32LE(0x46546c67, 0)
    header.writeUInt32LE(2, 4)
    header.writeUInt32LE(totalLength, 8)

    const jsonHeader = Buffer.alloc(8)
    jsonHeader.writeUInt32LE(jsonBuffer.length, 0)
    jsonHeader.writeUInt32LE(0x4e4f534a, 4)

    const binHeader = Buffer.alloc(8)
    binHeader.writeUInt32LE(binary.length, 0)
    binHeader.writeUInt32LE(0x004e4942, 4)

    return Buffer.concat([header, jsonHeader, jsonBuffer, binHeader, binary])
  }
}

function addPart(builder, name, geometry, material, transform = {}) {
  const mesh = builder.addGeometry(geometry, material, `${name}Mesh`)
  return builder.addNode({
    name,
    mesh,
    translation: transform.translation,
    rotation: transform.rotation,
    scale: transform.scale,
    children: transform.children,
  })
}

function rotationTrack(node, times, eulers) {
  const values = []
  for (const [x, y, z] of eulers) values.push(...toQuaternion(x, y, z))
  return { node, path: 'rotation', times, values }
}

function translationTrack(node, times, translations) {
  return { node, path: 'translation', times, values: translations.flat() }
}

function createCharacterGlb(agentName, profile) {
  const builder = new GlbBuilder()

  const materials = {
    skin: builder.addMaterial('Skin', profile.skin, 0.84),
    hair: builder.addMaterial('Hair', profile.hair, 0.94),
    jacket: builder.addMaterial('Jacket', profile.jacket, 0.8),
    shirt: builder.addMaterial('Shirt', profile.shirt, 0.78),
    trousers: builder.addMaterial('Trousers', profile.trousers, 0.88),
    shoes: builder.addMaterial('Shoes', profile.shoes, 0.92),
    accent: builder.addMaterial('Accent', profile.accent, 0.72),
    eyes: builder.addMaterial('Eyes', '#151820', 0.86),
    mouth: builder.addMaterial('Mouth', '#704c45', 0.86),
  }

  const leftShoe = addPart(
    builder,
    'LeftShoe',
    new THREE.BoxGeometry(0.21, 0.13, 0.36),
    materials.shoes,
    { translation: [0, -0.27, -0.08] },
  )
  const rightShoe = addPart(
    builder,
    'RightShoe',
    new THREE.BoxGeometry(0.21, 0.13, 0.36),
    materials.shoes,
    { translation: [0, -0.27, -0.08] },
  )

  const leftLeg = addPart(
    builder,
    'LeftLeg',
    new THREE.CylinderGeometry(0.1, 0.11, 0.52, 7),
    materials.trousers,
    {
      translation: [-0.16, 0.56, 0.08],
      children: [leftShoe],
    },
  )
  const rightLeg = addPart(
    builder,
    'RightLeg',
    new THREE.CylinderGeometry(0.1, 0.11, 0.52, 7),
    materials.trousers,
    {
      translation: [0.16, 0.56, 0.08],
      children: [rightShoe],
    },
  )

  const leftArm = addPart(
    builder,
    'LeftArm',
    new THREE.CylinderGeometry(0.085, 0.095, 0.6, 8),
    materials.jacket,
    {
      translation: [-0.36, 1.06, -0.02],
      rotation: toQuaternion(-0.35, 0, 0.12),
    },
  )
  const rightArm = addPart(
    builder,
    'RightArm',
    new THREE.CylinderGeometry(0.085, 0.095, 0.6, 8),
    materials.jacket,
    {
      translation: [0.36, 1.06, -0.02],
      rotation: toQuaternion(-0.35, 0, -0.12),
    },
  )

  const shirt = addPart(
    builder,
    'ShirtPanel',
    new THREE.BoxGeometry(0.2, 0.27, 0.04),
    materials.shirt,
    { translation: [0, 0.11, -0.31], rotation: toQuaternion(0.08, 0, 0) },
  )
  const tie = addPart(
    builder,
    'Tie',
    new THREE.BoxGeometry(0.045, 0.2, 0.028),
    materials.accent,
    { translation: [0, 0.04, -0.335] },
  )
  const torso = addPart(
    builder,
    'Torso',
    new THREE.CylinderGeometry(0.27, 0.35, 0.68, 6),
    materials.jacket,
    {
      translation: [0, 1.03, 0],
      children: [shirt, tie],
    },
  )

  const leftEye = addPart(
    builder,
    'LeftEye',
    new THREE.SphereGeometry(0.038, 8, 8),
    materials.eyes,
    { translation: [-0.12, 0.02, -0.31] },
  )
  const rightEye = addPart(
    builder,
    'RightEye',
    new THREE.SphereGeometry(0.038, 8, 8),
    materials.eyes,
    { translation: [0.12, 0.02, -0.31] },
  )
  const mouth = addPart(
    builder,
    'Mouth',
    new THREE.TorusGeometry(0.075, 0.013, 6, 12, Math.PI),
    materials.mouth,
    { translation: [0, -0.09, -0.325], rotation: toQuaternion(Math.PI / 2, 0, 0) },
  )

  const hairChildren = []
  const hairCap = addPart(
    builder,
    'HairCap',
    new THREE.IcosahedronGeometry(0.36, 1),
    materials.hair,
    { translation: [0, 0.2, 0.02], scale: [1.05, 0.72, 1.03] },
  )
  hairChildren.push(hairCap)

  if (profile.hairStyle === 'bob') {
    hairChildren.push(
      addPart(builder, 'HairLeft', new THREE.BoxGeometry(0.13, 0.44, 0.34), materials.hair, {
        translation: [-0.3, -0.02, 0],
      }),
      addPart(builder, 'HairRight', new THREE.BoxGeometry(0.13, 0.44, 0.34), materials.hair, {
        translation: [0.3, -0.02, 0],
      }),
    )
  } else if (profile.hairStyle === 'wave') {
    hairChildren.push(
      addPart(builder, 'HairWaveLeft', new THREE.IcosahedronGeometry(0.19, 1), materials.hair, {
        translation: [-0.24, 0.07, -0.01],
      }),
      addPart(builder, 'HairWaveRight', new THREE.IcosahedronGeometry(0.19, 1), materials.hair, {
        translation: [0.24, 0.07, -0.01],
      }),
    )
  } else if (profile.hairStyle === 'side' || profile.hairStyle === 'swept') {
    hairChildren.push(
      addPart(builder, 'HairSweep', new THREE.BoxGeometry(0.42, 0.14, 0.28), materials.hair, {
        translation: [profile.hairStyle === 'side' ? 0.14 : -0.1, 0.26, -0.17],
        rotation: toQuaternion(0.06, 0.05, profile.hairStyle === 'side' ? -0.35 : 0.4),
      }),
    )
  }

  const headMesh = builder.addGeometry(
    new THREE.IcosahedronGeometry(0.37, 2),
    materials.skin,
    'HeadMesh',
  )
  const head = builder.addNode({
    name: 'Head',
    mesh: headMesh,
    translation: [0, 1.5, 0],
    children: [leftEye, rightEye, mouth, ...hairChildren],
  })

  const root = builder.addNode({
    name: 'CharacterRoot',
    children: [torso, head, leftArm, rightArm, leftLeg, rightLeg],
  })

  const timesIdle = [0, 0.8, 1.6]
  builder.addAnimation('Idle', [
    translationTrack(root, timesIdle, [[0, 0, 0], [0, 0.025, 0], [0, 0, 0]]),
    rotationTrack(head, timesIdle, [[0, -0.04, 0], [0, 0.05, 0], [0, -0.04, 0]]),
  ])

  const timesWalk = [0, 0.3, 0.6]
  builder.addAnimation('Walk', [
    translationTrack(root, timesWalk, [[0, 0, 0], [0, 0.055, 0], [0, 0, 0]]),
    rotationTrack(leftArm, timesWalk, [[0.7, 0, 0.12], [-0.7, 0, 0.12], [0.7, 0, 0.12]]),
    rotationTrack(rightArm, timesWalk, [[-0.7, 0, -0.12], [0.7, 0, -0.12], [-0.7, 0, -0.12]]),
    rotationTrack(leftLeg, timesWalk, [[-0.65, 0, 0], [0.65, 0, 0], [-0.65, 0, 0]]),
    rotationTrack(rightLeg, timesWalk, [[0.65, 0, 0], [-0.65, 0, 0], [0.65, 0, 0]]),
  ])

  const timesSit = [0, 0.45]
  builder.addAnimation('Sit', [
    translationTrack(root, timesSit, [[0, 0, 0], [0, -0.18, 0.06]]),
    rotationTrack(torso, timesSit, [[0, 0, 0], [0.12, 0, 0]]),
    rotationTrack(leftLeg, timesSit, [[0, 0, 0], [-1.15, 0, 0]]),
    rotationTrack(rightLeg, timesSit, [[0, 0, 0], [-1.15, 0, 0]]),
    rotationTrack(leftArm, timesSit, [[-0.35, 0, 0.12], [-0.82, 0, 0.15]]),
    rotationTrack(rightArm, timesSit, [[-0.35, 0, -0.12], [-0.82, 0, -0.15]]),
  ])

  const timesTyping = [0, 0.16, 0.32, 0.48]
  builder.addAnimation('Typing', [
    translationTrack(root, timesTyping, [[0, -0.18, 0.06], [0, -0.16, 0.06], [0, -0.18, 0.06], [0, -0.16, 0.06]]),
    rotationTrack(torso, timesTyping, [[0.14, 0, 0], [0.15, 0, 0], [0.14, 0, 0], [0.15, 0, 0]]),
    rotationTrack(leftLeg, timesTyping, Array(4).fill([-1.15, 0, 0])),
    rotationTrack(rightLeg, timesTyping, Array(4).fill([-1.15, 0, 0])),
    rotationTrack(leftArm, timesTyping, [[-1.02, 0, 0.16], [-0.78, 0, 0.16], [-1.02, 0, 0.16], [-0.78, 0, 0.16]]),
    rotationTrack(rightArm, timesTyping, [[-0.78, 0, -0.16], [-1.02, 0, -0.16], [-0.78, 0, -0.16], [-1.02, 0, -0.16]]),
    rotationTrack(head, timesTyping, [[0.08, 0, 0], [0.05, 0.025, 0], [0.08, 0, 0], [0.05, -0.025, 0]]),
  ])

  const timesTalking = [0, 0.45, 0.9, 1.35]
  builder.addAnimation('Talking', [
    translationTrack(root, timesTalking, Array(4).fill([0, -0.18, 0.06])),
    rotationTrack(leftLeg, timesTalking, Array(4).fill([-1.15, 0, 0])),
    rotationTrack(rightLeg, timesTalking, Array(4).fill([-1.15, 0, 0])),
    rotationTrack(head, timesTalking, [[0, -0.12, 0], [0, 0.12, 0], [0, -0.08, 0], [0, 0.1, 0]]),
    rotationTrack(rightArm, timesTalking, [[-0.55, 0, -0.12], [-0.25, 0, -0.55], [-0.75, 0, -0.18], [-0.35, 0, -0.45]]),
    rotationTrack(leftArm, timesTalking, Array(4).fill([-0.55, 0, 0.12])),
  ])

  return builder.finish(root)
}

await fs.mkdir(outputDir, { recursive: true })

for (const [agentName, profile] of Object.entries(profiles)) {
  const fileName = `${agentName.toLowerCase()}.glb`
  const glb = createCharacterGlb(agentName, profile)
  await fs.writeFile(path.join(outputDir, fileName), glb)
  console.log(`generated ${fileName} (${Math.round(glb.length / 1024)} KB)`)
}
