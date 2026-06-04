/**
 * ScreenContainer — 모든 화면이 공유하는 기본 레이아웃
 *
 * - SafeArea + 다크 배경 + 일관된 패딩
 * - StepIndicator 자동 표시
 */

import React from 'react';
import { View, Text, Pressable, StyleSheet, StatusBar, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import StepIndicator from './StepIndicator';
import { APP_INFO } from '../constants/config';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function ScreenContainer({
  children,
  step,            // 'home' | 'keyword' | 'food' | 'restaurant'
  scroll = true,
  bottomBar,       // 하단 고정 영역 (예: 추천받기 버튼)
}) {
  const navigation = useNavigation();
  const Body = scroll ? ScrollView : View;
  const bodyProps = scroll
    ? { contentContainerStyle: styles.bodyScroll, showsVerticalScrollIndicator: false }
    : { style: styles.bodyFlex };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />
      {step && <GlobalHeader navigation={navigation} />}
      {step && <StepIndicator current={step} />}
      <Body {...bodyProps}>{children}</Body>
      {bottomBar && <View style={styles.bottomBar}>{bottomBar}</View>}
    </SafeAreaView>
  );
}

function GlobalHeader({ navigation }) {
  return (
    <View style={styles.header}>
      <Pressable
        onPress={() => navigation.navigate('Home')}
        style={({ pressed }) => [styles.brandWrap, pressed && styles.headerPressed]}
        hitSlop={8}
      >
        <Text style={styles.brand}>{APP_INFO.name}</Text>
        <Text style={styles.team}>by {APP_INFO.team}</Text>
      </Pressable>

      <Pressable
        onPress={() => navigation.navigate('MyPage')}
        style={({ pressed }) => [styles.myPageBtn, pressed && styles.myPageBtnPressed]}
        hitSlop={8}
      >
        <Text style={styles.myPageIcon}>👤</Text>
        <Text style={styles.myPageText}>마이</Text>
      </Pressable>
    </View>
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
    paddingTop: SPACING.md,
    paddingBottom: SPACING.xs,
    backgroundColor: COLORS.bg,
  },
  brandWrap: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  headerPressed: {
    opacity: 0.75,
  },
  brand: {
    fontSize: FONT.sizeXl,
    fontWeight: FONT.weightExtra,
    color: COLORS.primary,
  },
  team: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginLeft: SPACING.sm,
  },
  myPageBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  myPageBtnPressed: {
    backgroundColor: COLORS.surfaceAlt,
    borderColor: COLORS.primary,
  },
  myPageIcon: {
    fontSize: 14,
    marginRight: 4,
  },
  myPageText: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightMedium,
  },
});
