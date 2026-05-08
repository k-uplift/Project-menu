/**
 * StepIndicator — 상단 단계 표시
 *
 * 교수님 피드백 #1 반영:
 *   "핵심 흐름이 명확하게 보이도록"
 *   감성 입력 → 키워드 → 음식 → 음식점 → 상세
 *   네 단계의 진행도를 항상 상단에 노출
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS, SPACING, FONT } from '../constants/theme';

const STEPS = [
  { key: 'home', label: '입력' },
  { key: 'keyword', label: '키워드' },
  { key: 'food', label: '음식' },
  { key: 'restaurant', label: '음식점' },
];

export default function StepIndicator({ current }) {
  const currentIndex = STEPS.findIndex((s) => s.key === current);

  return (
    <View style={styles.wrap}>
      {STEPS.map((step, idx) => {
        const isActive = idx === currentIndex;
        const isPassed = idx < currentIndex;
        return (
          <React.Fragment key={step.key}>
            <View style={styles.stepCol}>
              <View
                style={[
                  styles.dot,
                  isPassed && styles.dotPassed,
                  isActive && styles.dotActive,
                ]}
              >
                <Text
                  style={[
                    styles.dotNum,
                    (isActive || isPassed) && styles.dotNumActive,
                  ]}
                >
                  {idx + 1}
                </Text>
              </View>
              <Text
                style={[
                  styles.label,
                  isActive && styles.labelActive,
                ]}
              >
                {step.label}
              </Text>
            </View>
            {idx < STEPS.length - 1 && (
              <View style={[styles.line, isPassed && styles.linePassed]} />
            )}
          </React.Fragment>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
  },
  stepCol: {
    alignItems: 'center',
  },
  dot: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotActive: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  dotPassed: {
    backgroundColor: COLORS.primaryDim,
    borderColor: COLORS.primaryDim,
  },
  dotNum: {
    fontSize: 11,
    color: COLORS.textMuted,
    fontWeight: FONT.weightBold,
  },
  dotNumActive: {
    color: '#1A0F08',
  },
  label: {
    fontSize: 10,
    color: COLORS.textMuted,
    marginTop: 4,
    fontWeight: FONT.weightMedium,
  },
  labelActive: {
    color: COLORS.primary,
    fontWeight: FONT.weightBold,
  },
  line: {
    flex: 1,
    height: 1,
    backgroundColor: COLORS.border,
    marginHorizontal: SPACING.xs,
    marginBottom: 16,
  },
  linePassed: {
    backgroundColor: COLORS.primaryDim,
  },
});
