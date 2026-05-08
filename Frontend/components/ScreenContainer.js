/**
 * ScreenContainer — 모든 화면이 공유하는 기본 레이아웃
 *
 * - SafeArea + 다크 배경 + 일관된 패딩
 * - StepIndicator 자동 표시
 */

import React from 'react';
import { View, StyleSheet, StatusBar, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import StepIndicator from './StepIndicator';
import { COLORS, SPACING } from '../constants/theme';

export default function ScreenContainer({
  children,
  step,            // 'home' | 'keyword' | 'food' | 'restaurant'
  scroll = true,
  bottomBar,       // 하단 고정 영역 (예: 추천받기 버튼)
}) {
  const Body = scroll ? ScrollView : View;
  const bodyProps = scroll
    ? { contentContainerStyle: styles.bodyScroll, showsVerticalScrollIndicator: false }
    : { style: styles.bodyFlex };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />
      {step && <StepIndicator current={step} />}
      <Body {...bodyProps}>{children}</Body>
      {bottomBar && <View style={styles.bottomBar}>{bottomBar}</View>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  bodyScroll: {
    paddingHorizontal: SPACING.lg,
    paddingBottom: SPACING.xl,
  },
  bodyFlex: {
    flex: 1,
    paddingHorizontal: SPACING.lg,
  },
  bottomBar: {
    paddingHorizontal: SPACING.lg,
    paddingTop: SPACING.md,
    paddingBottom: SPACING.lg,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    backgroundColor: COLORS.bg,
  },
});
