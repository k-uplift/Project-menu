/**
 * FoodCard — 음식 추천 카드 (이모지 → 썸네일로 교체)
 */

import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import FoodThumbnail from './FoodThumbnail';
import { COLORS, SPACING, RADIUS, FONT, SHADOW } from '../constants/theme';

export default function FoodCard({ food, selected = false, onPress }) {
  const { name, reason } = food;

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        SHADOW.card,
        selected && styles.cardSelected,
        pressed && styles.pressed,
      ]}
    >
      {/* 상단: 썸네일 + 이름 + 태그 */}
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <FoodThumbnail food={food} size="md" imageUrl={food.imageUrl} />
          <View style={styles.titleTextWrap}>
            <Text style={styles.name}>{name}</Text>
            <Text style={styles.tags} numberOfLines={1}>
              {(food.tags || []).slice(0, 3).map((t) => `#${t}`).join(' ')}
            </Text>
          </View>
        </View>
      </View>

      {/* 추천 근거 — CF 탭에서만 노출. 기본 탭은 근거가 카드마다 거의 같아
          (모두 '검색 키워드 일치') 생략하고, CF 탭만 '나와 닮은 사용자' 근거를 보여준다.
          base 응답은 cfScore=null, CF 응답은 cfScore 숫자라 이걸로 구분. */}
      {reason?.cfScore != null && reason?.cfDescription ? (
        <View style={styles.reasonBox}>
          <ReasonRow
            icon="🤝"
            title="취향 매칭"
            content={reason.cfDescription}
            highlight
          />
        </View>
      ) : null}
    </Pressable>
  );
}

function ReasonRow({ icon, title, content, highlight = false }) {
  return (
    <View style={styles.reasonRow}>
      <Text style={styles.reasonIcon}>{icon}</Text>
      <View style={{ flex: 1 }}>
        <Text style={[styles.reasonTitle, highlight && styles.reasonTitleHighlight]}>
          {title}
        </Text>
        <Text style={styles.reasonContent}>{content}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  cardSelected: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.surfaceAlt,
  },
  pressed: {
    opacity: 0.92,
  },

  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  titleTextWrap: {
    marginLeft: SPACING.md,
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  name: {
    fontSize: FONT.sizeLg,
    fontWeight: FONT.weightBold,
    color: COLORS.textPrimary,
    flexShrink: 1,
    marginRight: SPACING.sm,
  },
  tags: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    textAlign: 'right',
    flex: 1,
  },

  reasonBox: {
    backgroundColor: COLORS.bg,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    gap: SPACING.sm,
    marginTop: SPACING.md,
  },
  reasonRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  reasonIcon: {
    fontSize: 14,
    marginRight: SPACING.sm,
    marginTop: 2,
  },
  reasonTitle: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    fontWeight: FONT.weightMedium,
    marginBottom: 2,
  },
  reasonTitleHighlight: {
    color: COLORS.accent,
  },
  reasonContent: {
    fontSize: FONT.sizeSm,
    color: COLORS.textPrimary,
    lineHeight: 18,
  },
});
