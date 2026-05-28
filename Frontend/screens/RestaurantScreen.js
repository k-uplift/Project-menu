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
} from 'react-native';

import ScreenContainer from '../components/ScreenContainer';
import PrimaryButton from '../components/PrimaryButton';
import RestaurantCard from '../components/RestaurantCard';
import { getRestaurantsByFood } from '../services/restaurantService';
import { BASE_LOCATION } from '../services/contextService';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function RestaurantScreen({ route, navigation }) {
  const { food, query } = route.params;

  const [sort, setSort] = useState('distance');
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      try {
        const data = await getRestaurantsByFood(food, { sort, query });
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
    navigation.navigate('RestaurantDetail', { restaurant, food });
  };

  return (
    <ScreenContainer
      step="restaurant"
      bottomBar={
        <PrimaryButton
          label="처음부터 다시 찾기"
          variant="ghost"
          onPress={() => navigation.popToTop()}
        />
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
          label="취향 맞춤"
          subLabel="CF"
          active={sort === 'cf'}
          onPress={() => setSort('cf')}
        />
      </View>

      <Text style={styles.tabDesc}>
        {sort === 'distance'
          ? '한성대 기숙사에서 가까운 순서대로 보여드려요.'
          : '나와 취향이 비슷한 사용자들이 자주 방문한 곳이에요.'}
      </Text>

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
    marginBottom: SPACING.lg,
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
