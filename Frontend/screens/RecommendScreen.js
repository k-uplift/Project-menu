/**
 * RecommendScreen — 음식 추천 결과 (STEP 03)
 *
 * 변경:
 *  - 음식 카드 클릭 시 행동 추적 이벤트 전송 (+1점)
 *  - 같은 카드를 연속 클릭해도 중복 전송 방지 (이전 선택 ID와 비교)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  Pressable,
} from 'react-native';

import ScreenContainer from '../components/ScreenContainer';
import PrimaryButton from '../components/PrimaryButton';
import FoodCard from '../components/FoodCard';
import {
  getFoodRecommendations,
  getPersonalizedRecommendations,
} from '../services/recommendationService';
import {
  addRecentSearch,
  addRecentFood,
  toggleLikeFood,
  getLikedFoods,
} from '../services/userStorageService';
import { trackFoodCardClick } from '../services/behaviorTrackingService';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function RecommendScreen({ route, navigation }) {
  const { keywords, originalText, context: ctxParam } = route.params;

  const [tab, setTab] = useState('base');
  const [baseList, setBaseList] = useState([]);
  const [cfList, setCfList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshSeed, setRefreshSeed] = useState(0);
  const [selectedFoodId, setSelectedFoodId] = useState(null);
  const [likedIds, setLikedIds] = useState(new Set());

  const loadRecommendations = useCallback(
    async (seed) => {
      const ctx = { ...ctxParam, originalText, refreshSeed: seed };
      const [base, cf] = await Promise.all([
        getFoodRecommendations(keywords, ctx),
        getPersonalizedRecommendations(keywords, ctx),
      ]);
      return { base, cf };
    },
    [keywords, ctxParam, originalText]
  );

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      try {
        const { base, cf } = await loadRecommendations(0);
        if (!mounted) return;
        setBaseList(base);
        setCfList(cf);
        if (base.length > 0) setSelectedFoodId(base[0].id);

        await addRecentSearch(originalText, keywords);
        for (const food of base.slice(0, 3)) {
          await addRecentFood(food);
        }

        const liked = await getLikedFoods();
        if (mounted) setLikedIds(new Set(liked.map((f) => f.id)));
      } catch (e) {
        console.error(e);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [keywords, originalText, loadRecommendations]);

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      const newSeed = refreshSeed + 1;
      const { base, cf } = await loadRecommendations(newSeed);
      setBaseList(base);
      setCfList(cf);
      setRefreshSeed(newSeed);
      if (base.length > 0) setSelectedFoodId(base[0].id);
    } catch (e) {
      console.error(e);
    } finally {
      setRefreshing(false);
    }
  };

  const handleLike = async (food) => {
    const isNowLiked = await toggleLikeFood(food);
    setLikedIds((prev) => {
      const next = new Set(prev);
      if (isNowLiked) next.add(food.id);
      else next.delete(food.id);
      return next;
    });
  };

  // 음식 카드 클릭 — 행동 점수 +1점
  // 같은 카드를 다시 누르면 중복 전송 방지
  const handleFoodCardPress = (food) => {
    if (selectedFoodId !== food.id) {
      trackFoodCardClick(food); // fire-and-forget
    }
    setSelectedFoodId(food.id);
  };

  const currentList = tab === 'base' ? baseList : cfList;
  const selectedFood = currentList.find((f) => f.id === selectedFoodId) || currentList[0];

  const handleNext = () => {
    if (!selectedFood) return;
    navigation.navigate('Restaurant', { food: selectedFood, query: originalText });
  };

  const ctxLine = ctxParam
    ? `${ctxParam.timeCtx?.label || ''} · ${ctxParam.weatherCtx?.label || ''}`
    : '';

  return (
    <ScreenContainer
      step="food"
      bottomBar={
        <PrimaryButton
          label={selectedFood ? `${selectedFood.name} 음식점 찾기 →` : '음식을 선택해주세요'}
          onPress={handleNext}
          disabled={!selectedFood}
        />
      }
    >
      <View style={styles.titleRow}>
        <Text style={styles.title}>맞춤 메뉴 추천</Text>
        <Pressable
          onPress={() => navigation.goBack()}
          style={({ pressed }) => [styles.editBtn, pressed && styles.editBtnPressed]}
          hitSlop={8}
        >
          <Text style={styles.editBtnText}>✎ 키워드 수정</Text>
        </Pressable>
      </View>

      <View style={styles.metaRow}>
        <View style={styles.keywordRow}>
          {keywords.map((k) => (
            <Text key={k.id} style={styles.keywordText}>#{k.label}</Text>
          ))}
        </View>
        {ctxLine && (
          <View style={styles.ctxBadge}>
            <Text style={styles.ctxText}>{ctxLine}</Text>
          </View>
        )}
      </View>

      <View style={styles.tabBar}>
        <TabButton
          label="기본 추천"
          active={tab === 'base'}
          onPress={() => setTab('base')}
        />
        <TabButton
          label="나를 위한 추천"
          subLabel="CF"
          active={tab === 'cf'}
          onPress={() => setTab('cf')}
        />
      </View>

      <View style={styles.descRow}>
        <Text style={styles.tabDesc}>
          {tab === 'base'
            ? '키워드와 일치도가 높은 메뉴 순서대로 보여드려요.'
            : '나와 비슷한 취향의 사용자들이 자주 선택한 메뉴예요.'}
        </Text>
        <Pressable
          onPress={handleRefresh}
          disabled={refreshing || loading}
          style={({ pressed }) => [
            styles.refreshBtn,
            (refreshing || loading) && styles.refreshBtnDisabled,
            pressed && styles.refreshBtnPressed,
          ]}
          hitSlop={6}
        >
          <Text style={styles.refreshIcon}>{refreshing ? '⟳' : '↻'}</Text>
          <Text style={styles.refreshText}>
            {refreshing ? '추천 중...' : '다른 추천 보기'}
          </Text>
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.loadingBox}>
          <ActivityIndicator color={COLORS.primary} />
          <Text style={styles.loadingText}>맞춤 메뉴를 찾고 있어요...</Text>
        </View>
      ) : currentList.length === 0 ? (
        <View style={styles.loadingBox}>
          <Text style={styles.loadingText}>추천 결과가 없어요.</Text>
        </View>
      ) : (
        <>
          {currentList.map((food) => (
            <FoodCard
              key={`${food.id}-${refreshSeed}`}
              food={food}
              selected={selectedFoodId === food.id}
              liked={likedIds.has(food.id)}
              onPress={() => handleFoodCardPress(food)}
              onLikePress={() => handleLike(food)}
            />
          ))}

          {refreshSeed > 0 && (
            <Text style={styles.refreshNote}>
              💡 같은 키워드로 {refreshSeed}번째 추천을 받았어요
            </Text>
          )}

          <Text style={styles.dataNote}>
            현재는 더미 데이터로 동작합니다.{'\n'}
            추후 LLM + Matrix Factorization 기반 추천 엔진과 연결될 예정이에요.
          </Text>
        </>
      )}
    </ScreenContainer>
  );
}

function TabButton({ label, subLabel, active, onPress }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.tab, active && styles.tabActive]}
    >
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
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: SPACING.md,
    marginBottom: SPACING.sm,
  },
  title: {
    fontSize: FONT.sizeXl,
    fontWeight: FONT.weightExtra,
    color: COLORS.textPrimary,
  },
  editBtn: {
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  editBtnPressed: {
    backgroundColor: COLORS.surfaceAlt,
    borderColor: COLORS.primary,
  },
  editBtnText: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightMedium,
  },

  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.lg,
    flexWrap: 'wrap',
    gap: SPACING.sm,
  },
  keywordRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    flex: 1,
  },
  keywordText: {
    color: COLORS.primary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightMedium,
    marginRight: SPACING.sm,
  },
  ctxBadge: {
    backgroundColor: COLORS.surface,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 4,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  ctxText: {
    color: COLORS.textSecondary,
    fontSize: 11,
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

  descRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.lg,
  },
  tabDesc: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    flex: 1,
    lineHeight: 18,
    paddingRight: SPACING.sm,
  },
  refreshBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    backgroundColor: COLORS.primarySoft,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: COLORS.primary,
  },
  refreshBtnDisabled: {
    opacity: 0.5,
  },
  refreshBtnPressed: {
    opacity: 0.7,
  },
  refreshIcon: {
    color: COLORS.primary,
    fontSize: FONT.sizeMd,
    marginRight: 4,
    fontWeight: FONT.weightBold,
  },
  refreshText: {
    color: COLORS.primary,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightBold,
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

  refreshNote: {
    fontSize: FONT.sizeXs,
    color: COLORS.accent,
    textAlign: 'center',
    marginTop: SPACING.sm,
    marginBottom: SPACING.sm,
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
