/**
 * RestaurantCard — 음식점 카드
 *
 * 거리, 평점, 배달 여부, CF 매칭도 표시
 */

import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { COLORS, SPACING, RADIUS, FONT, SHADOW } from '../constants/theme';

export default function RestaurantCard({
  restaurant,
  index,
  onPress,
  showCfMatch = false,
  showRecommendedMenus = false,
}) {
  const {
    name,
    rating,
    reviewCount,
    distanceKm,
    walkMin,
    priceRange,
    recommendedPriceRange,
    delivery,
    cfMatch,
    menuItems = [],
  } = restaurant;

  // 가격은 *추천 음식(kind)* 가격 우선, 없으면 식당 전체 범위로 폴백.
  const displayPrice = recommendedPriceRange || priceRange;
  const recommendedMenuNames = menuItems
    .map((item) => item?.name)
    .filter(Boolean)
    .slice(0, 2);

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

        {displayPrice ? <Text style={styles.price}>{displayPrice}</Text> : null}

        {showRecommendedMenus && recommendedMenuNames.length > 0 && (
          <View style={styles.recommendedMenuBox}>
            <Text style={styles.recommendedMenuLabel}>추천메뉴</Text>
            <Text style={styles.recommendedMenuText} numberOfLines={1}>
              {recommendedMenuNames.join(' · ')}
            </Text>
          </View>
        )}

        {/* CF 매칭 표시 — 취향 정렬 모드 + cfMatch 데이터 있을 때만 */}
        {showCfMatch && cfMatch != null && (
          <View style={styles.cfBox}>
            <Text style={styles.cfLabel}>👥 취향 일치도</Text>
            <View style={styles.cfBarWrap}>
              <View style={[styles.cfBar, { width: `${Math.round(cfMatch * 100)}%` }]} />
            </View>
            <Text style={styles.cfPercent}>{Math.round(cfMatch * 100)}%</Text>
          </View>
        )}
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
  recommendedMenuBox: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    maxWidth: '100%',
    backgroundColor: COLORS.primarySoft,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    borderColor: COLORS.primary,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 4,
    marginTop: SPACING.xs,
  },
  recommendedMenuLabel: {
    color: COLORS.primary,
    fontSize: 10,
    fontWeight: FONT.weightBold,
    marginRight: SPACING.xs,
  },
  recommendedMenuText: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightBold,
    flexShrink: 1,
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

  cfBox: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: SPACING.sm,
  },
  cfLabel: {
    fontSize: 11,
    color: COLORS.textMuted,
    marginRight: SPACING.sm,
  },
  cfBarWrap: {
    flex: 1,
    height: 4,
    backgroundColor: COLORS.border,
    borderRadius: 2,
    overflow: 'hidden',
    marginRight: SPACING.sm,
  },
  cfBar: {
    height: '100%',
    backgroundColor: COLORS.primary,
    borderRadius: 2,
  },
  cfPercent: {
    fontSize: 11,
    color: COLORS.primary,
    fontWeight: FONT.weightBold,
    minWidth: 32,
    textAlign: 'right',
  },
});
