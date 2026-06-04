/**
 * RestaurantDetailScreen — 음식점 상세 (STEP 5)
 *
 * 변경:
 *  - 메뉴 섹션을 *추천 메뉴 강조* + *전체 메뉴 목록* 두 섹션으로 분리
 *  - 진입 시 `getAllMenusByStore`로 그 식당의 *전체* 메뉴 추가 로드
 *  - 평점·배달·시그니처·CF 매칭도 같은 stub 값이면 안 보이게 가드
 *  - 길찾기/배달의민족 행동 추적 이벤트 유지
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Alert,
  Linking,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import PrimaryButton from '../components/PrimaryButton';
import {
  trackNavigateClick,
  trackDeliveryClick,
} from '../services/behaviorTrackingService';
import { getAllMenusByStore } from '../services/restaurantService';
import { COLORS, SPACING, RADIUS, FONT, SHADOW } from '../constants/theme';

export default function RestaurantDetailScreen({ route, navigation }) {
  const { restaurant, food, sessionId = null, userId = 1 } = route.params;

  // 그 식당 전체 메뉴 (추천 흐름과 무관하게 그 식당이 파는 모든 메뉴)
  // restaurant.menuItems는 *선택한 kind에 매칭된* 메뉴만 들어 있어 "메뉴 적다"
  // 인상을 줘서 별도 fetch.
  const [allMenus, setAllMenus] = useState([]);
  const [menusLoading, setMenusLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setMenusLoading(true);
      const menus = await getAllMenusByStore(restaurant.storeId || restaurant.id);
      if (mounted) {
        setAllMenus(menus);
        setMenusLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [restaurant.storeId, restaurant.id]);

  // 길찾기 (카카오맵으로 연결 — 가장 보편적인 지도 앱)
  const handleNavigate = async () => {
    // 행동 점수 +2점 — fire-and-forget (await 없이 호출)
    trackNavigateClick(restaurant, food, { sessionId, userId });

    // 이름만으로 검색하면 *전국 동명 식당*이 잡혀 엉뚱한 곳으로 가는 경우가 많다.
    // 주소에서 구(예: 성북구) + 법정동(괄호 안, 예: 동소문동2가)을 뽑아 함께 검색해
    // 같은 이름 다른 지역과 구분한다. 주소 없으면 이름만으로 폴백.
    const addr = restaurant.address || '';
    const gu = (addr.match(/(\S+구)(?:\s|$)/) || [])[1] || '';
    const dong = (addr.match(/\(([^,)]+)/) || [])[1] || '';
    const area = [gu, dong].filter(Boolean).join(' ');
    const query = encodeURIComponent(area ? `${restaurant.name} ${area}` : restaurant.name);
    const url = `https://map.kakao.com/?q=${query}`;

    try {
      const canOpen = await Linking.canOpenURL(url);
      if (canOpen) {
        Linking.openURL(url);
      } else {
        Alert.alert('연결 실패', '지도 앱을 열 수 없어요.');
      }
    } catch (e) {
      Alert.alert(
        '길찾기',
        `카카오맵에서 "${restaurant.name}" 검색 결과로 이동합니다.\n\n(시연 환경에서는 실제 이동되지 않을 수 있어요)`
      );
    }
  };

  // 배달 연결 — 3단 우선순위:
  //   ① restaurant.baeminUrl (시연용 수동 매핑) — 배민 식당 페이지 직행
  //   ② restaurant.naverPlaceId — 네이버 플레이스 *배달 탭* 직행
  //                              (배민·요기요·쿠팡이츠 통합 노출. 식당 324/330=98%)
  //   ③ 카카오맵 검색 fallback — 결손 6개 식당용. 카카오맵은 *반드시* 검색 결과
  //                              페이지 열림, 매칭 식당의 *카카오 주문 통합* 노출
  //                              (baemin.me/search는 404 위험 있어 카카오로 교체)
  const handleDelivery = async () => {
    // 행동 점수 +2점
    trackDeliveryClick(restaurant, food, { sessionId, userId });

    let url, label;
    if (restaurant.baeminUrl) {
      url = restaurant.baeminUrl;
      label = '배달의민족';
    } else if (restaurant.naverPlaceId) {
      url = `https://m.place.naver.com/restaurant/${restaurant.naverPlaceId}/order/delivery`;
      label = '네이버 주문';
    } else {
      url = `https://map.kakao.com/?q=${encodeURIComponent(restaurant.name)}`;
      label = '카카오맵';
    }

    try {
      const canOpen = await Linking.canOpenURL(url);
      if (canOpen) {
        Linking.openURL(url);
      } else {
        Alert.alert('연결 실패', `${label} 페이지를 열 수 없어요.`);
      }
    } catch (e) {
      Alert.alert(
        label,
        `"${restaurant.name}" 페이지로 이동합니다.\n\n(시연 환경에서는 실제 이동되지 않을 수 있어요)`
      );
    }
  };

  // 별점 렌더링 (rating > 0일 때만 표시)
  const renderStars = () => {
    const r = restaurant.rating || 0;
    const full = Math.floor(r);
    const half = r - full >= 0.5;
    return '★'.repeat(full) + (half ? '★' : '') + '☆'.repeat(5 - full - (half ? 1 : 0));
  };

  // 추천 메뉴(매칭) 이름 집합 — 전체 메뉴에서 추천 메뉴 제외 시 사용
  const recommendedMenus = restaurant.menuItems || [];
  const recommendedNames = new Set(recommendedMenus.map((m) => m.name));
  const otherMenus = allMenus.filter((m) => !recommendedNames.has(m.name));

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      {/* 상단 헤더 */}
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
        {/* 헤더 카드 */}
        <View style={[styles.headerCard, SHADOW.card]}>
          <View style={styles.headerOrb} />
          {restaurant.delivery && (
            <View style={styles.deliveryBadge}>
              <Text style={styles.deliveryText}>배달 가능</Text>
            </View>
          )}
          <Text style={styles.headerCategory}>{restaurant.category}</Text>
          <Text style={styles.headerName}>{restaurant.name}</Text>
        </View>

        {/* 평점 — 데이터가 있을 때만 (현재 백엔드에 없으면 안 보임) */}
        {restaurant.rating > 0 && (
          <View style={styles.ratingRow}>
            <Text style={styles.starText}>{renderStars()}</Text>
            <Text style={styles.ratingNum}>{restaurant.rating.toFixed(1)}</Text>
            {restaurant.reviewCount > 0 && (
              <Text style={styles.reviewCount}>({restaurant.reviewCount}개 리뷰)</Text>
            )}
          </View>
        )}

        {/* 정보 카드 */}
        <View style={styles.infoCard}>
          <InfoRow icon="📍" text={restaurant.address} />
          <InfoRow
            icon="🕐"
            text={[
              restaurant.hours,
              restaurant.closedDay ? `${restaurant.closedDay} 휴무` : '휴무 없음',
            ]
              .filter(Boolean)
              .join(' · ')}
          />
          {(restaurant.recommendedPriceRange || restaurant.priceRange) ? (
            <InfoRow
              icon="💰"
              text={restaurant.recommendedPriceRange || restaurant.priceRange}
            />
          ) : null}
          {food && (
            <InfoRow
              icon="🎯"
              text={`"${food.name}"을(를) 검색해서 찾았어요`}
              accent
            />
          )}
        </View>

        {/* 추천 메뉴 — 사용자가 검색한 종류의 매칭 메뉴 강조 */}
        {recommendedMenus.length > 0 && (
          <>
            <Text style={styles.sectionLabel}>
              🎯 추천 메뉴 {food?.name ? `· ${food.name}` : ''}
            </Text>
            <View style={[styles.menuCard, styles.menuCardRecommended]}>
              {recommendedMenus.map((item, idx) => (
                <MenuRowItem
                  key={`rec-${item.name}-${idx}`}
                  item={item}
                  isLast={idx === recommendedMenus.length - 1}
                />
              ))}
            </View>
          </>
        )}

        {/* 전체 메뉴 — 그 식당의 다른 모든 메뉴 */}
        <Text style={styles.sectionLabel}>
          전체 메뉴 {allMenus.length > 0 ? `(${allMenus.length})` : ''}
        </Text>
        <View style={styles.menuCard}>
          {menusLoading ? (
            <View style={{ paddingVertical: SPACING.lg, alignItems: 'center' }}>
              <ActivityIndicator color={COLORS.primary} />
            </View>
          ) : otherMenus.length > 0 ? (
            otherMenus.map((item, idx) => (
              <MenuRowItem
                key={`all-${item.name}-${idx}`}
                item={item}
                isLast={idx === otherMenus.length - 1}
              />
            ))
          ) : allMenus.length === 0 ? (
            <Text style={styles.menuEmpty}>메뉴 정보가 없어요</Text>
          ) : (
            <Text style={styles.menuEmpty}>
              추천 메뉴 외 다른 메뉴 정보가 없어요
            </Text>
          )}
        </View>

        {/* CF 매칭도 */}
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

        {/* === 최종 선택 영역 === */}
        <Text style={styles.sectionLabel}>최종 선택</Text>

        <View style={styles.finalRow}>
          {/* 길찾기 — 카카오맵 그린 */}
          <FinalButton
            label="길찾기"
            icon="🗺️"
            color="#03C75A"
            textColor="#FFFFFF"
            onPress={handleNavigate}
          />
          {/* 배달 — 배민/네이버 주문 등으로 연결 */}
          <FinalButton
            label="배달"
            icon="🛵"
            color="#2AC1BC"
            textColor="#FFFFFF"
            onPress={handleDelivery}
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

/** 메뉴 한 줄 — 추천/일반 공용. 가격은 백엔드가 원본 문자열로 줌 */
function MenuRowItem({ item, isLast }) {
  return (
    <View style={[styles.menuRow, isLast && styles.menuRowLast]}>
      <View style={styles.menuLeft}>
        <Text style={styles.menuName}>{item.name}</Text>
        {item.isSignature && (
          <View style={styles.signatureBadge}>
            <Text style={styles.signatureText}>대표</Text>
          </View>
        )}
      </View>
      {item.price ? (
        <Text style={styles.menuPrice}>
          {String(item.price).includes('원') ? item.price : `${item.price}원`}
        </Text>
      ) : null}
    </View>
  );
}

/** 최종 선택 버튼 */
function FinalButton({ label, icon, color, textColor, onPress }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.finalBtn,
        { backgroundColor: color },
        pressed && styles.finalBtnPressed,
      ]}
    >
      <Text style={styles.finalIcon}>{icon}</Text>
      <Text style={[styles.finalLabel, { color: textColor }]}>{label}</Text>
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

  sectionLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
    fontWeight: FONT.weightBold,
    marginBottom: SPACING.sm,
    marginTop: SPACING.sm,
  },

  menuCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.md,
    marginBottom: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  menuCardRecommended: {
    backgroundColor: COLORS.primarySoft,
    borderColor: COLORS.primary,
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

  // === 최종 선택 영역 (2개 버튼) ===
  finalRow: {
    flexDirection: 'row',
    gap: SPACING.sm,
    marginBottom: SPACING.lg,
  },
  finalBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: SPACING.lg,
    borderRadius: RADIUS.lg,
  },
  finalBtnPressed: {
    opacity: 0.85,
    transform: [{ scale: 0.98 }],
  },
  finalIcon: {
    fontSize: 20,
    marginRight: SPACING.sm,
  },
  finalLabel: {
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightExtra,
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
