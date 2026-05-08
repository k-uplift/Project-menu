/**
 * RestaurantDetailScreen — 음식점 상세 정보 (STEP 5)
 *
 * 첨부 이미지 디자인 그대로:
 *  - 상단 대형 헤더 카드 (배달 배지 + 카테고리 + 음식점 이름)
 *  - 평점 표시
 *  - 정보 카드 (주소, 영업시간, 가격대)
 *  - 메뉴 목록 (대표 메뉴 강조)
 *  - 4개 외부 연결 버튼 (배민/요기요/카카오맵/네이버지도)
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Alert,
  Linking,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import PrimaryButton from '../components/PrimaryButton';
import { COLORS, SPACING, RADIUS, FONT, SHADOW } from '../constants/theme';

export default function RestaurantDetailScreen({ route, navigation }) {
  const { restaurant, food } = route.params;

  // 외부 플랫폼 검색 URL 연결
  const openExternal = async (platform) => {
    const query = encodeURIComponent(restaurant.name);
    let url = '';
    let appName = '';
    switch (platform) {
      case 'baemin':
        url = `https://baemin.me/search?query=${query}`;
        appName = '배달의민족';
        break;
      case 'yogiyo':
        url = `https://www.yogiyo.co.kr/mobile/#/?search=${query}`;
        appName = '요기요';
        break;
      case 'kakao':
        url = `https://map.kakao.com/?q=${query}`;
        appName = '카카오맵';
        break;
      case 'naver':
        url = `https://map.naver.com/v5/search/${query}`;
        appName = '네이버지도';
        break;
    }

    try {
      const canOpen = await Linking.canOpenURL(url);
      if (canOpen) {
        Linking.openURL(url);
      } else {
        Alert.alert('연결 실패', '해당 앱을 열 수 없어요.');
      }
    } catch (e) {
      Alert.alert(
        appName,
        `"${restaurant.name}" 검색 결과로 이동합니다.\n\n(시연 환경에서는 실제 이동되지 않을 수 있어요)`
      );
    }
  };

  // 별점 렌더링 (5점 만점)
  const renderStars = () => {
    const full = Math.floor(restaurant.rating);
    const half = restaurant.rating - full >= 0.5;
    const stars = '★'.repeat(full) + (half ? '★' : '') + '☆'.repeat(5 - full - (half ? 1 : 0));
    return stars;
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      {/* 상단 헤더 (뒤로가기) */}
      <View style={styles.topBar}>
        <Pressable onPress={() => navigation.goBack()} style={styles.backBtn} hitSlop={12}>
          <Text style={styles.backText}>‹ 뒤로</Text>
        </Pressable>
        <View style={styles.brandWrap}>
          <Text style={styles.brand}>me:nu</Text>
        </View>
        <View style={styles.dashes}>
          {[...Array(5)].map((_, i) => (
            <View key={i} style={styles.dash} />
          ))}
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* 헤더 카드 — 첨부 이미지 그대로 */}
        <View style={[styles.headerCard, SHADOW.card]}>
          {/* 우측 상단 장식 점 */}
          <View style={styles.headerOrb} />

          {restaurant.delivery && (
            <View style={styles.deliveryBadge}>
              <Text style={styles.deliveryText}>배달 가능</Text>
            </View>
          )}

          <Text style={styles.headerCategory}>{restaurant.category}</Text>
          <Text style={styles.headerName}>{restaurant.name}</Text>
        </View>

        {/* 평점 */}
        <View style={styles.ratingRow}>
          <Text style={styles.starText}>{renderStars()}</Text>
          <Text style={styles.ratingNum}>{restaurant.rating.toFixed(1)}</Text>
          <Text style={styles.reviewCount}>({restaurant.reviewCount}개 리뷰)</Text>
        </View>

        {/* 정보 카드 */}
        <View style={styles.infoCard}>
          <InfoRow icon="📍" text={restaurant.address} />
          <InfoRow
            icon="🕐"
            text={`${restaurant.hours} · ${restaurant.closedDay} 휴무`}
          />
          <InfoRow icon="💰" text={restaurant.priceRange} />
          {food && (
            <InfoRow
              icon="🎯"
              text={`"${food.name}"을(를) 검색해서 찾았어요`}
              accent
            />
          )}
        </View>

        {/* 메뉴 목록 */}
        <Text style={styles.sectionLabel}>메뉴</Text>
        <View style={styles.menuCard}>
          {restaurant.menuItems && restaurant.menuItems.length > 0 ? (
            restaurant.menuItems.map((item, idx) => (
              <View
                key={`${item.name}-${idx}`}
                style={[
                  styles.menuRow,
                  idx === restaurant.menuItems.length - 1 && styles.menuRowLast,
                ]}
              >
                <View style={styles.menuLeft}>
                  <Text style={styles.menuName}>{item.name}</Text>
                  {item.isSignature && (
                    <View style={styles.signatureBadge}>
                      <Text style={styles.signatureText}>대표</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.menuPrice}>
                  {item.price.toLocaleString()}원
                </Text>
              </View>
            ))
          ) : (
            <Text style={styles.menuEmpty}>메뉴 정보가 없어요</Text>
          )}
        </View>

        {/* CF 매칭도 (있을 때만) */}
        {restaurant.cfMatch && (
          <View style={styles.cfBox}>
            <Text style={styles.cfLabel}>👥 취향 일치도</Text>
            <View style={styles.cfBarWrap}>
              <View
                style={[
                  styles.cfBar,
                  { width: `${Math.round(restaurant.cfMatch * 100)}%` },
                ]}
              />
            </View>
            <Text style={styles.cfPercent}>
              {Math.round(restaurant.cfMatch * 100)}%
            </Text>
          </View>
        )}

        <Text style={styles.sectionLabel}>플랫폼에서 보기</Text>

        {/* 외부 연결 버튼 4개 — 첨부 이미지처럼 2x2 그리드 */}
        <View style={styles.platformGrid}>
          <PlatformButton
            label="배달의민족"
            color="#2AC1BC"
            onPress={() => openExternal('baemin')}
          />
          <PlatformButton
            label="요기요"
            color="#FA0050"
            onPress={() => openExternal('yogiyo')}
          />
          <PlatformButton
            label="카카오맵"
            color="#FEE500"
            textColor="#1A0F08"
            onPress={() => openExternal('kakao')}
          />
          <PlatformButton
            label="네이버지도"
            color="#03C75A"
            onPress={() => openExternal('naver')}
          />
        </View>

        {/* 처음으로 다시 */}
        <View style={{ marginTop: SPACING.lg }}>
          <PrimaryButton
            label="처음부터 다시 찾기"
            variant="ghost"
            onPress={() => navigation.popToTop()}
          />
        </View>

        <Text style={styles.dataNote}>
          💡 현재는 더미 데이터입니다.{'\n'}
          추후 음식점 DB + 공공데이터 메뉴 API와 연결됩니다.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

/** 정보 한 줄 */
function InfoRow({ icon, text, accent = false }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoIcon}>{icon}</Text>
      <Text style={[styles.infoText, accent && styles.infoTextAccent]}>{text}</Text>
    </View>
  );
}

/** 플랫폼 버튼 */
function PlatformButton({ label, color, textColor = '#FFFFFF', onPress }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.platformBtn,
        { backgroundColor: color },
        pressed && styles.platformPressed,
      ]}
    >
      <Text style={[styles.platformText, { color: textColor }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },

  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
  },
  backBtn: {
    paddingVertical: 4,
    paddingRight: SPACING.md,
  },
  backText: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightMedium,
  },
  brandWrap: {
    flex: 1,
    alignItems: 'center',
  },
  brand: {
    fontSize: FONT.sizeLg,
    fontWeight: FONT.weightExtra,
    color: COLORS.primary,
    letterSpacing: -0.5,
  },
  dashes: {
    flexDirection: 'row',
    gap: 3,
  },
  dash: {
    width: 8,
    height: 2,
    backgroundColor: COLORS.primary,
    borderRadius: 1,
  },

  scrollContent: {
    paddingHorizontal: SPACING.lg,
    paddingBottom: SPACING.xxl,
  },

  // === 헤더 카드 ===
  headerCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
    paddingVertical: SPACING.xl,
    marginBottom: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    overflow: 'hidden',
    minHeight: 140,
  },
  headerOrb: {
    position: 'absolute',
    top: 16,
    right: 16,
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: COLORS.primaryDim,
    opacity: 0.7,
  },
  deliveryBadge: {
    alignSelf: 'flex-start',
    backgroundColor: COLORS.primarySoft,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 4,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    borderColor: COLORS.primary,
    marginBottom: SPACING.md,
  },
  deliveryText: {
    color: COLORS.primary,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightBold,
  },
  headerCategory: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    marginBottom: SPACING.xs,
  },
  headerName: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeXxl,
    fontWeight: FONT.weightExtra,
    letterSpacing: -0.5,
  },

  // === 평점 ===
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.md,
    paddingHorizontal: SPACING.xs,
  },
  starText: {
    color: COLORS.warning,
    fontSize: FONT.sizeMd,
    marginRight: SPACING.sm,
    letterSpacing: 1,
  },
  ratingNum: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightBold,
    marginRight: SPACING.sm,
  },
  reviewCount: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeSm,
  },

  // === 정보 카드 ===
  infoCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    marginBottom: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: SPACING.sm,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  infoIcon: {
    fontSize: 14,
    marginRight: SPACING.sm,
    marginTop: 1,
    width: 20,
  },
  infoText: {
    flex: 1,
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    lineHeight: 20,
  },
  infoTextAccent: {
    color: COLORS.primary,
    fontWeight: FONT.weightMedium,
  },

  // === 섹션 라벨 ===
  sectionLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
    fontWeight: FONT.weightBold,
    marginBottom: SPACING.sm,
    marginTop: SPACING.sm,
  },

  // === 메뉴 카드 ===
  menuCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.md,
    marginBottom: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  menuRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: SPACING.md,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  menuRowLast: {
    borderBottomWidth: 0,
  },
  menuLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  menuName: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightMedium,
    marginRight: SPACING.sm,
  },
  signatureBadge: {
    backgroundColor: COLORS.primarySoft,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  signatureText: {
    color: COLORS.primary,
    fontSize: 10,
    fontWeight: FONT.weightBold,
  },
  menuPrice: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
  },
  menuEmpty: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeSm,
    textAlign: 'center',
    paddingVertical: SPACING.lg,
  },

  // === CF 매칭도 ===
  cfBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    marginBottom: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  cfLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textSecondary,
    marginRight: SPACING.sm,
  },
  cfBarWrap: {
    flex: 1,
    height: 6,
    backgroundColor: COLORS.bg,
    borderRadius: 3,
    overflow: 'hidden',
    marginRight: SPACING.sm,
  },
  cfBar: {
    height: '100%',
    backgroundColor: COLORS.primary,
    borderRadius: 3,
  },
  cfPercent: {
    fontSize: FONT.sizeXs,
    color: COLORS.primary,
    fontWeight: FONT.weightBold,
    minWidth: 36,
    textAlign: 'right',
  },

  // === 플랫폼 버튼 그리드 (2x2) ===
  platformGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: SPACING.sm,
    marginBottom: SPACING.lg,
  },
  platformBtn: {
    flexBasis: '48%',
    flexGrow: 1,
    paddingVertical: SPACING.md,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  platformPressed: {
    opacity: 0.85,
    transform: [{ scale: 0.98 }],
  },
  platformText: {
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
  },

  dataNote: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    textAlign: 'center',
    marginTop: SPACING.lg,
    lineHeight: 18,
    fontStyle: 'italic',
  },
});
