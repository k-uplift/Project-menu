/**
 * KeywordTag — 키워드 칩 컴포넌트
 *
 * - 선택된 상태 / 비선택 / 추가 버튼 등 다양한 상태를 지원
 */

import React from 'react';
import { Pressable, Text, StyleSheet } from 'react-native';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function KeywordTag({
  label,
  selected = true,
  onPress,
  variant = 'default', // 'default' | 'suggest' | 'add'
  showRemove = false,
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.tag,
        selected ? styles.selected : styles.unselected,
        variant === 'suggest' && styles.suggest,
        variant === 'add' && styles.add,
        pressed && styles.pressed,
      ]}
    >
      <Text
        style={[
          styles.text,
          selected ? styles.textSelected : styles.textUnselected,
          variant === 'suggest' && styles.textSuggest,
        ]}
      >
        {variant === 'add' ? `+ ${label}` : `#${label}`}
        {showRemove && selected && '  ×'}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tag: {
    paddingVertical: SPACING.sm,
    paddingHorizontal: SPACING.md,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
  },
  selected: {
    backgroundColor: COLORS.primarySoft,
    borderColor: COLORS.primary,
  },
  unselected: {
    backgroundColor: 'transparent',
    borderColor: COLORS.border,
  },
  suggest: {
    backgroundColor: COLORS.surface,
    borderColor: COLORS.border,
  },
  add: {
    backgroundColor: 'transparent',
    borderColor: COLORS.border,
    borderStyle: 'dashed',
  },
  pressed: {
    opacity: 0.7,
  },
  text: {
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightMedium,
  },
  textSelected: {
    color: COLORS.primary,
  },
  textUnselected: {
    color: COLORS.textMuted,
    textDecorationLine: 'line-through',
  },
  textSuggest: {
    color: COLORS.textSecondary,
    textDecorationLine: 'none',
  },
});
