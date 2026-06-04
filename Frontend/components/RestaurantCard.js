/**
 * RestaurantCard — 음식점 카드
 *
 * 거리, 평점, 배달 여부 표시
 */

import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { COLORS, SPACING, RADIUS, FONT, SHADOW } from '../constants/theme';

export default function RestaurantCard({
  restaurant,
  index,
  onPress,
  showRecommendedMenus = false,
}) {
  const {
    name,
    rating,
    reviewCount,
    distanceKm,
    walkMin,
    priceRange,
    delivery,
    menuItems = [],
  } = restaurant;
  const recommendedMenuNames = menuItems
    .map((item) => item.name)
    .filter(Boolean)
    .slice(0, 3)
    .join(', ');

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, SHADOW.card, pressed && styles.pressed]}
    >
      {/* 인덱스 핀 */}
      <View style={styles.pin}>
        <Text style={styles.pinNum}>{index + 1}</Text>
      </View>

      {/* 본문 */}
      <View style={styles.body}>
        <View style={styles.topRow}>
          <Text style={styles.name} numberOfLines={1}>
            {name}
          </Text>
          {delivery && <DeliveryBadge />}
        </View>

        {/* 평점 + 거리 — 평점 데이터 없으면(현재 백엔드) 거리만 표시 */}
        <View style={styles.metaRow}>
          {rating > 0 && (
            <>
              <Text style={styles.star}>★</Text>
              <Text style={styles.rating}>{rating.toFixed(1)}</Text>
              {reviewCount > 0 && (
                <Text style={styles.reviewCount}>({reviewCount})</Text>
              )}
              {distanceKm != null && <Text style={styles.dot}>·</Text>}
            </>
          )}
          {distanceKm != null && (
            <Text style={styles.meta}>
              {distanceKm}km{walkMin != null ? ` · 도보 ${walkMin}분` : ''}
            </Text>
          )}
        </View>

        {priceRange ? <Text style={styles.price}>{priceRange}</Text> : null}

        {showRecommendedMenus && recommendedMenuNames ? (
          <View style={styles.recommendedBox}>
            <Text style={styles.recommendedLabel}>추천 메뉴</Text>
            <Text style={styles.recommendedText} numberOfLines={2}>
              {recommendedMenuNames}
            </Text>
          </View>
        ) : null}

      </View>
    </Pressable>
  );
}

function DeliveryBadge() {
  return (
    <View style={styles.deliveryBadge}>
      <Text style={styles.deliveryText}>배달</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  pressed: {
    opacity: 0.9,
  },
  pin: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
    marginTop: 2,
  },
  pinNum: {
    color: '#1A0F08',
    fontWeight: FONT.weightExtra,
    fontSize: FONT.sizeSm,
  },
  body: {
    flex: 1,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  name: {
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightBold,
    color: COLORS.textPrimary,
    flex: 1,
    marginRight: SPACING.sm,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
    flexWrap: 'wrap',
  },
  star: {
    color: COLORS.warning,
    fontSize: FONT.sizeSm,
    marginRight: 2,
  },
  rating: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
    marginRight: 4,
  },
  reviewCount: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
  },
  dot: {
    color: COLORS.textMuted,
    marginHorizontal: SPACING.xs,
  },
  meta: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeXs,
  },
  price: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
  },
  recommendedBox: {
    marginTop: SPACING.sm,
    backgroundColor: COLORS.primarySoft,
    borderRadius: RADIUS.sm,
    paddingHorizontal: SPACING.sm,
    paddingVertical: SPACING.sm,
    borderWidth: 1,
    borderColor: COLORS.primaryDim,
  },
  recommendedLabel: {
    color: COLORS.primary,
    fontSize: 10,
    fontWeight: FONT.weightBold,
    marginBottom: 2,
  },
  recommendedText: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeXs,
    lineHeight: 17,
    fontWeight: FONT.weightMedium,
  },
  deliveryBadge: {
    backgroundColor: COLORS.primarySoft,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 2,
    borderRadius: RADIUS.sm,
  },
  deliveryText: {
    color: COLORS.primary,
    fontSize: 11,
    fontWeight: FONT.weightBold,
  },
});
