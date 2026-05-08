/**
 * FoodCard — 음식 추천 카드 (이모지 → 썸네일로 교체)
 */

import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import FoodThumbnail from './FoodThumbnail';
import { COLORS, SPACING, RADIUS, FONT, SHADOW } from '../constants/theme';

export default function FoodCard({
  food,
  selected = false,
  liked = false,
  onPress,
  onLikePress,
}) {
  const { name, score, reason } = food;

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
      {/* 상단: 썸네일 + 이름 + 좋아요 + 점수 */}
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

        <View style={styles.headerRight}>
          {onLikePress && (
            <Pressable
              onPress={(e) => {
                e.stopPropagation && e.stopPropagation();
                onLikePress();
              }}
              hitSlop={10}
              style={({ pressed }) => [
                styles.likeBtn,
                pressed && styles.likeBtnPressed,
              ]}
            >
              <Text style={[styles.likeIcon, liked && styles.likeIconActive]}>
                {liked ? '♥' : '♡'}
              </Text>
            </Pressable>
          )}
          <ScoreBadge score={score} />
        </View>
      </View>

      {/* 추천 이유 — 3종 명시적 분리 */}
      <View style={styles.reasonBox}>
        <ReasonRow
          icon="🎯"
          title="감성 매칭"
          content={
            reason.matchedKeywords.length > 0
              ? reason.matchedKeywords.map((k) => `#${k}`).join(' ')
              : '키워드 없음'
          }
        />
        <ReasonRow
          icon="👥"
          title="유사 사용자"
          content={reason.cfDescription}
          highlight
        />
        <ReasonRow icon="🌧️" title="지금 상황" content={reason.contextNote} />
      </View>
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

function ScoreBadge({ score }) {
  return (
    <View style={styles.scoreBadge}>
      <Text style={styles.scoreNum}>{score}</Text>
      <Text style={styles.scoreUnit}>점</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
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
    marginBottom: SPACING.md,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  titleTextWrap: {
    marginLeft: SPACING.md,
    flex: 1,
  },
  name: {
    fontSize: FONT.sizeLg,
    fontWeight: FONT.weightBold,
    color: COLORS.textPrimary,
    marginBottom: 2,
  },
  tags: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
  },

  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  likeBtn: {
    paddingHorizontal: SPACING.sm,
    paddingVertical: 2,
    marginRight: SPACING.xs,
  },
  likeBtnPressed: {
    opacity: 0.6,
  },
  likeIcon: {
    fontSize: 22,
    color: COLORS.textMuted,
  },
  likeIconActive: {
    color: COLORS.danger,
  },

  scoreBadge: {
    flexDirection: 'row',
    alignItems: 'baseline',
    backgroundColor: COLORS.primarySoft,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    borderRadius: RADIUS.pill,
  },
  scoreNum: {
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightExtra,
    color: COLORS.primary,
  },
  scoreUnit: {
    fontSize: FONT.sizeXs,
    color: COLORS.primary,
    marginLeft: 2,
  },

  reasonBox: {
    backgroundColor: COLORS.bg,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    gap: SPACING.sm,
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
