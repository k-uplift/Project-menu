/**
 * MyPageScreen — 마이페이지
 *
 * 표시 항목:
 *  1. 사용자 선호 태그 (검색 키워드 빈도 자동 집계)
 *  2. 최근 추천 메뉴
 *  3. 최근 검색 키워드
 *
 * 좋아요 기능 제거 — CF 신호 단일화(implicit-only). 선호 태그는 검색
 * 키워드 빈도가 source가 된다 (사용자 자기 발화 = 가장 명확한 선호 표현).
 *
 * 추후 백엔드 연결 시:
 *  - userStorageService 의 함수 시그니처는 그대로 유지
 *  - 내부만 fetch 로 교체하면 자동으로 마이페이지도 동기화
 */

import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';

import {
  getRecentSearches,
  getRecentFoods,
  getPreferredTags,
  clearAllUserData,
} from '../services/userStorageService';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function MyPageScreen({ navigation }) {
  const [searches, setSearches] = useState([]);
  const [recentFoods, setRecentFoods] = useState([]);
  const [preferredTags, setPreferredTags] = useState([]);

  // 화면이 포커스될 때마다 데이터 새로 불러오기
  // (검색하고 돌아오면 선호 태그·이력이 즉시 반영되도록)
  useFocusEffect(
    useCallback(() => {
      let mounted = true;
      (async () => {
        const [s, r, t] = await Promise.all([
          getRecentSearches(),
          getRecentFoods(),
          getPreferredTags(),
        ]);
        if (!mounted) return;
        setSearches(s);
        setRecentFoods(r);
        setPreferredTags(t);
      })();
      return () => {
        mounted = false;
      };
    }, [])
  );

  // 최근 검색 다시 사용
  const handleReuseSearch = (search) => {
    // 키워드를 다시 KeywordScreen 으로 보내서 수정 가능하게
    const keywords = search.keywords.map((label, idx) => ({
      id: `kw-history-${idx}-${Date.now()}`,
      label,
      confidence: 1.0,
      source: 'user',
    }));
    navigation.navigate('Keyword', {
      analyzeResult: {
        originalText: search.originalText,
        keywords,
      },
    });
  };

  // 데이터 전체 초기화
  const handleClear = () => {
    Alert.alert(
      '모든 기록을 지울까요?',
      '검색 이력, 좋아요, 추천 이력이 모두 삭제됩니다.',
      [
        { text: '취소', style: 'cancel' },
        {
          text: '삭제',
          style: 'destructive',
          onPress: async () => {
            await clearAllUserData();
            setSearches([]);
            setRecentFoods([]);
            setPreferredTags([]);
          },
        },
      ]
    );
  };

  const isEmpty =
    searches.length === 0 && recentFoods.length === 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      {/* 상단 바 */}
      <View style={styles.topBar}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={12}>
          <Text style={styles.backText}>‹ 뒤로</Text>
        </Pressable>
        <Text style={styles.topTitle}>마이페이지</Text>
        <Pressable onPress={handleClear} hitSlop={12}>
          <Text style={styles.clearText}>전체 삭제</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {isEmpty && (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyEmoji}>🍽️</Text>
            <Text style={styles.emptyTitle}>아직 기록이 없어요</Text>
            <Text style={styles.emptyDesc}>
              메뉴를 추천받고 좋아요를 눌러보세요.{'\n'}
              사용할수록 더 정확한 추천을 받을 수 있어요.
            </Text>
            <Pressable
              onPress={() => navigation.popToTop()}
              style={({ pressed }) => [
                styles.emptyBtn,
                pressed && { opacity: 0.85 },
              ]}
            >
              <Text style={styles.emptyBtnText}>지금 추천받기 →</Text>
            </Pressable>
          </View>
        )}

        {/* 1. 선호 태그 */}
        {preferredTags.length > 0 && (
          <Section
            title="내 선호 태그"
            subtitle="검색 키워드에서 자주 등장한 표현이에요"
            icon="🏷️"
          >
            <View style={styles.tagWrap}>
              {preferredTags.map(({ tag, count }) => (
                <View key={tag} style={styles.preferTag}>
                  <Text style={styles.preferTagText}>#{tag}</Text>
                  <Text style={styles.preferTagCount}>{count}</Text>
                </View>
              ))}
            </View>
          </Section>
        )}

        {/* 2. 최근 추천받은 메뉴 */}
        {recentFoods.length > 0 && (
          <Section
            title="최근 추천 메뉴"
            subtitle={`최근 ${recentFoods.length}개`}
            icon="🕘"
          >
            {recentFoods.map((food) => (
              <View key={food.id} style={styles.foodRow}>
                <Text style={styles.foodEmoji}>{food.emoji}</Text>
                <View style={styles.foodInfo}>
                  <Text style={styles.foodName}>{food.name}</Text>
                  <Text style={styles.foodTime}>
                    {formatRelativeTime(food.timestamp)}
                  </Text>
                </View>
              </View>
            ))}
          </Section>
        )}

        {/* 3. 최근 검색 */}
        {searches.length > 0 && (
          <Section
            title="최근 검색"
            subtitle="탭하면 같은 키워드로 다시 추천받아요"
            icon="🔎"
          >
            {searches.map((s) => (
              <Pressable
                key={s.id}
                onPress={() => handleReuseSearch(s)}
                style={({ pressed }) => [
                  styles.searchRow,
                  pressed && styles.searchRowPressed,
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.searchText} numberOfLines={1}>
                    "{s.originalText}"
                  </Text>
                  <View style={styles.searchKeywordRow}>
                    {s.keywords.slice(0, 4).map((kw, idx) => (
                      <Text key={idx} style={styles.searchKeyword}>
                        #{kw}
                      </Text>
                    ))}
                  </View>
                </View>
                <Text style={styles.searchTime}>
                  {formatRelativeTime(s.timestamp)}
                </Text>
              </Pressable>
            ))}
          </Section>
        )}

        <Text style={styles.footerNote}>
          모든 데이터는 기기에만 저장돼요{'\n'}
          (추후 백엔드 연결 예정)
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

/** 섹션 컴포넌트 */
function Section({ title, subtitle, icon, iconColor, children }) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        {icon && (
          <Text style={[styles.sectionIcon, iconColor && { color: iconColor }]}>
            {icon}
          </Text>
        )}
        <Text style={styles.sectionTitle}>{title}</Text>
        {subtitle && <Text style={styles.sectionSub}>· {subtitle}</Text>}
      </View>
      {children}
    </View>
  );
}

/** 시간 포맷 */
function formatRelativeTime(ts) {
  if (!ts) return '';
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  const hour = Math.floor(min / 60);
  const day = Math.floor(hour / 24);

  if (min < 1) return '방금';
  if (min < 60) return `${min}분 전`;
  if (hour < 24) return `${hour}시간 전`;
  if (day < 7) return `${day}일 전`;

  const date = new Date(ts);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },

  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
  },
  backText: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightMedium,
  },
  topTitle: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightBold,
  },
  clearText: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
  },

  scrollContent: {
    paddingHorizontal: SPACING.lg,
    paddingBottom: SPACING.xxl,
  },

  emptyBox: {
    alignItems: 'center',
    paddingVertical: SPACING.xxxl * 1.5,
  },
  emptyEmoji: {
    fontSize: 48,
    marginBottom: SPACING.md,
  },
  emptyTitle: {
    fontSize: FONT.sizeLg,
    color: COLORS.textPrimary,
    fontWeight: FONT.weightBold,
    marginBottom: SPACING.sm,
  },
  emptyDesc: {
    fontSize: FONT.sizeSm,
    color: COLORS.textMuted,
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: SPACING.xl,
  },
  emptyBtn: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: SPACING.xl,
    paddingVertical: SPACING.md,
    borderRadius: RADIUS.lg,
  },
  emptyBtnText: {
    color: '#1A0F08',
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
  },

  // === 섹션 ===
  section: {
    marginTop: SPACING.lg,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.md,
  },
  sectionIcon: {
    fontSize: 16,
    marginRight: SPACING.sm,
  },
  sectionTitle: {
    fontSize: FONT.sizeMd,
    color: COLORS.textPrimary,
    fontWeight: FONT.weightBold,
  },
  sectionSub: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginLeft: SPACING.xs,
  },

  // === 선호 태그 ===
  tagWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: SPACING.sm,
  },
  preferTag: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.primarySoft,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: COLORS.primary,
  },
  preferTagText: {
    color: COLORS.primary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
    marginRight: SPACING.xs,
  },
  preferTagCount: {
    color: COLORS.primary,
    fontSize: 11,
    backgroundColor: COLORS.bg,
    paddingHorizontal: 6,
    borderRadius: 10,
    fontWeight: FONT.weightBold,
  },

  // === 음식 행 ===
  foodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: SPACING.sm,
  },
  foodEmoji: {
    fontSize: 24,
    marginRight: SPACING.md,
  },
  foodInfo: {
    flex: 1,
  },
  foodName: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
    marginBottom: 2,
  },
  foodTime: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
  },

  // === 최근 검색 ===
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: SPACING.sm,
  },
  searchRowPressed: {
    backgroundColor: COLORS.surfaceAlt,
    borderColor: COLORS.primary,
  },
  searchText: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontStyle: 'italic',
    marginBottom: 4,
  },
  searchKeywordRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  searchKeyword: {
    color: COLORS.primary,
    fontSize: FONT.sizeXs,
    marginRight: SPACING.xs,
  },
  searchTime: {
    color: COLORS.textMuted,
    fontSize: 11,
    marginLeft: SPACING.sm,
  },

  footerNote: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    textAlign: 'center',
    marginTop: SPACING.xl,
    lineHeight: 18,
    fontStyle: 'italic',
  },
});
