import type { AgentStatus } from '../../types'

export interface CharacterPose {
  bodyY: number
  bodyTilt: number
  headTurn: number
  leftArmX: number
  rightArmX: number
  leftArmZ: number
  rightArmZ: number
  leftLegX: number
  rightLegX: number
}

export function getCharacterPose(status: AgentStatus, time: number): CharacterPose {
  const breathe = Math.sin(time * 2.2) * 0.012

  if (status === 'WORKING') {
    return {
      bodyY: 0.02 + Math.sin(time * 5.2) * 0.022,
      bodyTilt: -0.09,
      headTurn: Math.sin(time * 1.8) * 0.035,
      leftArmX: -0.92 + Math.sin(time * 12) * 0.24,
      rightArmX: -0.92 + Math.sin(time * 12 + Math.PI) * 0.24,
      leftArmZ: 0.14,
      rightArmZ: -0.14,
      leftLegX: 0,
      rightLegX: 0,
    }
  }

  if (status === 'DONE') {
    return {
      bodyY: 0.04 + Math.abs(Math.sin(time * 3)) * 0.035,
      bodyTilt: 0,
      headTurn: 0,
      leftArmX: -0.15,
      rightArmX: -0.15,
      leftArmZ: 0.42,
      rightArmZ: -0.42,
      leftLegX: 0,
      rightLegX: 0,
    }
  }

  if (status === 'ERROR') {
    return {
      bodyY: 0.02 + breathe,
      bodyTilt: 0.02,
      headTurn: Math.sin(time * 8) * 0.12,
      leftArmX: -0.25,
      rightArmX: -0.25,
      leftArmZ: 0.24,
      rightArmZ: -0.24,
      leftLegX: 0,
      rightLegX: 0,
    }
  }

  return {
    bodyY: 0.02 + breathe,
    bodyTilt: 0,
    headTurn: Math.sin(time * 0.8) * 0.025,
    leftArmX: -0.35,
    rightArmX: -0.35,
    leftArmZ: 0.12,
    rightArmZ: -0.12,
    leftLegX: 0,
    rightLegX: 0,
  }
}
