/**
 * LoadingOverlay — AI 분석 중 화면 (개선판)
 *
 * 사용자에게 시스템이 어떤 단계를 거치고 있는지 명확하게 표시
 *  ① 문장 구조 파싱
 *  ② 감성/맥락 추출
 *  ③ 키워드 매핑
 *  ④ 결과 정리
 *
 * 각 단계마다:
 *  - 현재 진행 중인 단계는 펄스 애니메이션 + 주황색 강조
 *  - 완료된 단계는 체크 표시
 *  - 대기 중인 단계는 회색
 */

import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated, Easing } from 'react-native';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

// 분석 단계 정의 — 실제 LLM 파이프라인 흐름을 반영
const ANALYSIS_STEPS = [
  {
    icon: '🔍',
    title: '문장 구조 파싱',
    description: '입력하신 문장을 토큰 단위로 분해하고 있어요',
    duration: 700,
  },
  {
    icon: '💭',
    title: '감성·맥락 추출',
    description: '문장 안의 감정과 상황을 이해하고 있어요',
    duration: 1000,
  },
  {
    icon: '🏷️',
    title: '키워드 매핑',
    description: 'Claude API가 음식 추천용 키워드를 생성 중이에요',
    duration: 1100,
  },
  {
    icon: '✨',
    title: '결과 정리',
    description: '추출된 키워드를 검수하고 있어요',
    duration: 700,
  },
];

export const TOTAL_LOADING_MS = ANALYSIS_STEPS.reduce(
  (sum, s) => sum + s.duration,
  0
); // 총 3500ms

export default function LoadingOverlay({ originalText }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [percent, setPercent] = useState(0); // 0~100 정수
  const progress = useRef(new Animated.Value(0)).current; // 0~1
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // 진행률 listener — 0~1 값을 0~100 정수로 변환해서 state 업데이트
  // (interpolate한 값에 listener를 붙이면 동작 안 할 수 있어서, 원본에 직접 붙임)
  useEffect(() => {
    const id = progress.addListener(({ value }) => {
      setPercent(Math.round(value * 100));
    });
    return () => progress.removeListener(id);
  }, [progress]);

  // 단계별로 진행
  useEffect(() => {
    let cancelled = false;
    let totalElapsed = 0;
    const timeouts = [];

    const advance = (idx) => {
      if (cancelled || idx >= ANALYSIS_STEPS.length) return;
      setCurrentStep(idx);

      const step = ANALYSIS_STEPS[idx];
      totalElapsed += step.duration;
      const targetProgress = totalElapsed / TOTAL_LOADING_MS;

      // 진행 바 애니메이션 (useNativeDriver: false — width 애니메이션은 native driver 불가)
      Animated.timing(progress, {
        toValue: targetProgress,
        duration: step.duration,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: false,
      }).start();

      // 다음 단계 예약
      const tid = setTimeout(() => advance(idx + 1), step.duration);
      timeouts.push(tid);
    };

    advance(0);

    return () => {
      cancelled = true;
      timeouts.forEach(clearTimeout);
    };
  }, [progress]);

  // 현재 단계 펄스 애니메이션 (점멸 효과)
  useEffect(() => {
    pulseAnim.setValue(1);
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 0.4,
          duration: 600,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 1,
          duration: 600,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [currentStep, pulseAnim]);

  const barWidth = progress.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  });

  return (
    <View style={styles.wrap}>
      <View style={styles.card}>
        {/* 헤더 */}
        <View style={styles.headerRow}>
          <Text style={styles.title}>AI 분석 중</Text>
          <Text style={styles.percent}>{percent}%</Text>
        </View>

        {/* 진행 바 */}
        <View style={styles.barWrap}>
          <Animated.View style={[styles.bar, { width: barWidth }]} />
        </View>

        {/* 단계 목록 */}
        <View style={styles.stepList}>
          {ANALYSIS_STEPS.map((step, idx) => {
            const isDone = idx < currentStep;
            const isActive = idx === currentStep;
            return (
              <Animated.View
                key={step.title}
                style={[
                  styles.stepRow,
                  isActive && { opacity: pulseAnim },
                ]}
              >
                {/* 좌측 아이콘 영역 */}
                <View
                  style={[
                    styles.stepIconWrap,
                    isDone && styles.stepIconDone,
                    isActive && styles.stepIconActive,
                  ]}
                >
                  <Text style={styles.stepIcon}>
                    {isDone ? '✓' : step.icon}
                  </Text>
                </View>

                {/* 텍스트 */}
                <View style={styles.stepTextWrap}>
                  <Text
                    style={[
                      styles.stepTitle,
                      isDone && styles.stepTitleDone,
                      isActive && styles.stepTitleActive,
                    ]}
                  >
                    {step.title}
                  </Text>
                  {(isActive || isDone) && (
                    <Text style={styles.stepDesc}>{step.description}</Text>
                  )}
                </View>
              </Animated.View>
            );
          })}
        </View>

        {/* 입력 원문 미리보기 */}
        {originalText && (
          <View style={styles.preview}>
            <Text style={styles.previewLabel}>분석 중인 문장</Text>
            <Text style={styles.previewText}>"{originalText}"</Text>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
  },
  card: {
    width: '100%',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl,
    padding: SPACING.xl,
    borderWidth: 1,
    borderColor: COLORS.border,
  },

  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.lg,
  },
  title: {
    fontSize: FONT.sizeLg,
    color: COLORS.textPrimary,
    fontWeight: FONT.weightExtra,
  },
  percent: {
    fontSize: FONT.sizeMd,
    color: COLORS.primary,
    fontWeight: FONT.weightExtra,
    minWidth: 50,
    textAlign: 'right',
  },

  barWrap: {
    height: 6,
    backgroundColor: COLORS.bg,
    borderRadius: 3,
    overflow: 'hidden',
    marginBottom: SPACING.xl,
  },
  bar: {
    height: '100%',
    backgroundColor: COLORS.primary,
    borderRadius: 3,
  },

  stepList: {
    gap: SPACING.md,
    marginBottom: SPACING.xl,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  stepIconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: COLORS.bg,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  stepIconActive: {
    backgroundColor: COLORS.primarySoft,
    borderColor: COLORS.primary,
  },
  stepIconDone: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  stepIcon: {
    fontSize: 16,
  },
  stepTextWrap: {
    flex: 1,
  },
  stepTitle: {
    fontSize: FONT.sizeSm,
    color: COLORS.textMuted,
    fontWeight: FONT.weightMedium,
  },
  stepTitleActive: {
    color: COLORS.textPrimary,
    fontWeight: FONT.weightBold,
  },
  stepTitleDone: {
    color: COLORS.textSecondary,
    fontWeight: FONT.weightMedium,
  },
  stepDesc: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginTop: 2,
    lineHeight: 16,
  },

  preview: {
    backgroundColor: COLORS.bg,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderLeftWidth: 3,
    borderLeftColor: COLORS.primary,
  },
  previewLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginBottom: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  previewText: {
    fontSize: FONT.sizeSm,
    color: COLORS.textPrimary,
    fontStyle: 'italic',
    lineHeight: 20,
  },
});
