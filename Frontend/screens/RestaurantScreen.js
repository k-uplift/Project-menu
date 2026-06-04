/**
 * RestaurantScreen — 음식점 추천 결과 (STEP 04)
 *
 * 추가:
 *  - 상단에 현재 위치 (한성대 기숙사) 표시
 *  - 거리/도보시간은 좌표 기반 자동 계산된 값 사용
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  Pressable,
  ScrollView,
  PanResponder,
} from 'react-native';

import ScreenContainer from '../components/ScreenContainer';
import PrimaryButton from '../components/PrimaryButton';
import RestaurantCard from '../components/RestaurantCard';
import { getRestaurantsByFood } from '../services/restaurantService';
import { BASE_LOCATION } from '../services/contextService';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function RestaurantScreen({ route, navigation }) {
  const { food, query, sessionId = null, userId = 1 } = route.params;

  const [sort, setSort] = useState('distance');
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      try {
        const data = await getRestaurantsByFood(food, { sort, query, userId });
        if (mounted) setList(data);
      } catch (e) {
        console.error(e);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [food.id, sort, query]);

  const handleRestaurantPress = (restaurant) => {
    navigation.navigate('RestaurantDetail', { restaurant, food, sessionId, userId });
  };

  return (
    <ScreenContainer
      step="restaurant"
      bottomBar={
        <View style={styles.bottomActions}>
          <View style={styles.bottomLeft}>
            <PrimaryButton
              label="메뉴 다시 고르기"
              variant="ghost"
              onPress={() => navigation.goBack()}
            />
          </View>
          <View style={styles.bottomRight}>
            <PrimaryButton
              label="처음부터 다시 찾기"
              variant="ghost"
              onPress={() => navigation.popToTop()}
            />
          </View>
        </View>
      }
    >
      <Text style={styles.title}>{food.name} 음식점</Text>

      {/* 현재 위치 표시 */}
      <View style={styles.locationBox}>
        <Text style={styles.locationIcon}>📍</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.locationLabel}>현재 위치 기준</Text>
          <Text style={styles.locationName}>{BASE_LOCATION.name}</Text>
        </View>
      </View>

      <Text style={styles.sub}>
        주변에서 {food.name}을(를) 파는 곳을 찾았어요.{'\n'}
        음식점을 탭하면 상세 정보를 볼 수 있어요.
      </Text>

      {/* 정렬 탭 */}
      <View style={styles.tabBar}>
        <SortTab
          label="거리순"
          active={sort === 'distance'}
          onPress={() => setSort('distance')}
        />
        <SortTab
          label="취향 매칭"
          subLabel="CF"
          active={sort === 'cf'}
          onPress={() => setSort('cf')}
        />
      </View>

      <Text style={styles.tabDesc}>
        {sort === 'distance'
          ? '한성대 기숙사에서 가까운 순서대로 보여드려요.'
          : '나와 비슷한 취향 사용자들이 좋아하는 메뉴가 많은 식당 순이에요.'}
      </Text>

      {sort === 'distance' && <MapPreview restaurants={list} />}

      {loading ? (
        <View style={styles.loadingBox}>
          <ActivityIndicator color={COLORS.primary} />
          <Text style={styles.loadingText}>음식점을 찾고 있어요...</Text>
        </View>
      ) : (
        <>
          {list.map((r, idx) => (
            <RestaurantCard
              key={r.id}
              restaurant={r}
              index={idx}
              showCfMatch={sort === 'cf'}
              showRecommendedMenus={sort === 'cf'}
              onPress={() => handleRestaurantPress(r)}
            />
          ))}

          <Text style={styles.dataNote}>
            💡 현재는 더미 데이터입니다.{'\n'}
            추후 카카오맵 / 네이버 API + 음식점 DB와 연결됩니다.
          </Text>
        </>
      )}
    </ScreenContainer>
  );
}

function MapPreview({ restaurants }) {
  const visibleRestaurants = restaurants;
  const canvasWidth = Math.max(1120, 250 + visibleRestaurants.length * 118);
  const dashCount = Math.max(18, visibleRestaurants.length * 5);
  const scrollRef = React.useRef(null);
  const scrollXRef = React.useRef(0);
  const dragStartXRef = React.useRef(0);
  const panResponder = React.useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gestureState) =>
          Math.abs(gestureState.dx) > 3 &&
          Math.abs(gestureState.dx) > Math.abs(gestureState.dy),
        onPanResponderGrant: () => {
          dragStartXRef.current = scrollXRef.current;
        },
        onPanResponderMove: (_, gestureState) => {
          const nextX = Math.max(0, dragStartXRef.current - gestureState.dx);
          scrollRef.current?.scrollTo({ x: nextX, animated: false });
        },
      }),
    []
  );

  return (
    <View style={styles.mapBox}>
      <ScrollView
        ref={scrollRef}
        horizontal
        scrollEnabled
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.routeMapContent}
        scrollEventThrottle={16}
        onScroll={(event) => {
          scrollXRef.current = event.nativeEvent.contentOffset.x;
        }}
      >
        <View
          style={[styles.routeCanvas, { width: canvasWidth }]}
          {...panResponder.panHandlers}
        >
          <View style={styles.routeSideBlockLeft} />
          <View style={styles.routeSideBlockRight} />
          <View style={styles.routeLineShadow} />
          <View style={styles.routeLine} />
          <View style={styles.routeDashRow}>
            {Array.from({ length: dashCount }).map((_, idx) => (
              <View key={idx} style={styles.routeDash} />
            ))}
          </View>

          <View style={styles.baseStop}>
            <View style={styles.baseMarker}>
              <Text style={styles.baseMarkerText}>현위치</Text>
            </View>
            <Text style={styles.stopCaption}>{BASE_LOCATION.name}</Text>
          </View>

          {visibleRestaurants.map((restaurant, idx) => (
            <View
              key={restaurant.id}
              style={[styles.routeStop, { left: 190 + idx * 118 }]}
            >
              <View style={styles.restaurantMarker}>
                <Text style={styles.restaurantMarkerText}>{idx + 1}</Text>
              </View>
              <Text style={styles.stopCaption} numberOfLines={1}>
                {restaurant.name}
              </Text>
              {restaurant.walkMin != null && (
                <Text style={styles.stopMeta}>도보 {restaurant.walkMin}분</Text>
              )}
            </View>
          ))}
        </View>
      </ScrollView>
      <View style={styles.mapFooter}>
        <Text style={styles.mapTitle}>거리순 경로 프리뷰</Text>
        <Text style={styles.mapSub}>가로로 드래그하면 후보 {visibleRestaurants.length}곳을 순서대로 볼 수 있어요.</Text>
      </View>
    </View>
  );
}

function SortTab({ label, subLabel, active, onPress }) {
  return (
    <Pressable onPress={onPress} style={[styles.tab, active && styles.tabActive]}>
      <Text style={[styles.tabText, active && styles.tabTextActive]}>{label}</Text>
      {subLabel && (
        <View style={[styles.tabSubBadge, active && styles.tabSubBadgeActive]}>
          <Text style={[styles.tabSubText, active && styles.tabSubTextActive]}>
            {subLabel}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bottomActions: {
    flexDirection: 'row',
    gap: SPACING.sm,
    alignItems: 'stretch',
  },
  bottomLeft: {
    flex: 0.9,
  },
  bottomRight: {
    flex: 1.1,
  },

  title: {
    fontSize: FONT.sizeXl,
    fontWeight: FONT.weightExtra,
    color: COLORS.textPrimary,
    marginTop: SPACING.md,
    marginBottom: SPACING.md,
  },

  locationBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.primarySoft,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    borderLeftWidth: 3,
    borderLeftColor: COLORS.primary,
    marginBottom: SPACING.md,
  },
  locationIcon: {
    fontSize: 18,
    marginRight: SPACING.sm,
  },
  locationLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginBottom: 2,
  },
  locationName: {
    fontSize: FONT.sizeSm,
    color: COLORS.primary,
    fontWeight: FONT.weightBold,
  },

  sub: {
    fontSize: FONT.sizeSm,
    color: COLORS.textSecondary,
    marginBottom: SPACING.lg,
    lineHeight: 20,
  },

  tabBar: {
    flexDirection: 'row',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    padding: 4,
    marginBottom: SPACING.sm,
  },
  tab: {
    flex: 1,
    paddingVertical: SPACING.sm,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    borderRadius: RADIUS.sm,
  },
  tabActive: {
    backgroundColor: COLORS.primary,
  },
  tabText: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightMedium,
  },
  tabTextActive: {
    color: '#1A0F08',
    fontWeight: FONT.weightBold,
  },
  tabSubBadge: {
    backgroundColor: COLORS.bg,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 4,
    marginLeft: SPACING.xs,
  },
  tabSubBadgeActive: {
    backgroundColor: '#1A0F08',
  },
  tabSubText: {
    fontSize: 9,
    color: COLORS.textMuted,
    fontWeight: FONT.weightBold,
  },
  tabSubTextActive: {
    color: COLORS.primary,
  },
  tabDesc: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginBottom: SPACING.md,
  },

  mapBox: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    overflow: 'hidden',
    marginBottom: SPACING.lg,
  },
  routeMapContent: {
    paddingRight: SPACING.lg,
  },
  routeCanvas: {
    height: 126,
    backgroundColor: '#1F2A24',
    position: 'relative',
    overflow: 'hidden',
  },
  routeSideBlockLeft: {
    position: 'absolute',
    left: 36,
    top: 12,
    width: 210,
    height: 34,
    borderRadius: RADIUS.md,
    backgroundColor: '#24322B',
  },
  routeSideBlockRight: {
    position: 'absolute',
    right: 58,
    bottom: 10,
    width: 260,
    height: 38,
    borderRadius: RADIUS.md,
    backgroundColor: '#24322B',
  },
  routeLineShadow: {
    position: 'absolute',
    left: 44,
    right: 44,
    top: 54,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#121916',
  },
  routeLine: {
    position: 'absolute',
    left: 44,
    right: 44,
    top: 59,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#3E5148',
  },
  routeDashRow: {
    position: 'absolute',
    left: 74,
    top: 62,
    flexDirection: 'row',
    gap: 30,
  },
  routeDash: {
    width: 28,
    height: 3,
    borderRadius: 2,
    backgroundColor: '#AFA69C',
    opacity: 0.55,
  },
  baseStop: {
    position: 'absolute',
    left: 34,
    top: 28,
    width: 118,
    alignItems: 'center',
  },
  routeStop: {
    position: 'absolute',
    top: 26,
    width: 104,
    alignItems: 'center',
  },
  baseMarker: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 5,
    borderRadius: RADIUS.pill,
    borderWidth: 2,
    borderColor: COLORS.bg,
  },
  baseMarkerText: {
    color: '#1A0F08',
    fontSize: 10,
    fontWeight: FONT.weightBold,
  },
  restaurantMarker: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.surface,
    borderWidth: 2,
    borderColor: COLORS.primary,
  },
  restaurantMarkerText: {
    color: COLORS.primary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightExtra,
  },
  stopCaption: {
    color: COLORS.textPrimary,
    fontSize: 10,
    fontWeight: FONT.weightBold,
    marginTop: 7,
    maxWidth: 96,
    textAlign: 'center',
  },
  stopMeta: {
    color: COLORS.textMuted,
    fontSize: 10,
    marginTop: 2,
  },
  mapFooter: {
    paddingHorizontal: SPACING.md,
    paddingTop: SPACING.sm,
    paddingBottom: SPACING.md,
  },
  mapTitle: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
    marginBottom: 2,
  },
  mapSub: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
  },

  loadingBox: {
    paddingVertical: SPACING.xxxl,
    alignItems: 'center',
  },
  loadingText: {
    color: COLORS.textMuted,
    marginTop: SPACING.sm,
    fontSize: FONT.sizeSm,
  },

  dataNote: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    textAlign: 'center',
    marginTop: SPACING.md,
    marginBottom: SPACING.md,
    lineHeight: 18,
    fontStyle: 'italic',
  },
});
