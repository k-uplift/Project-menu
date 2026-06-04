/**
 * MyPageScreen — 마이페이지
 *
 * 표시 항목:
 *  1. 취향 프로필 카드 — 달성한 칭호 1~4개 + 통계 (시도 종류·식당·검색 수)
 *  2. 내 선호 태그 (검색 키워드 빈도 자동 집계)
 *  3. 칭호 도감 (X/29) — 5 카테고리(A 시드 / B 장르 / C 음식 / D 행동 / E 메타)
 *  4. 최근 추천 메뉴
 *  5. 최근 검색 키워드
 *
 * 좋아요 기능 제거 — CF 신호 단일화(implicit-only). 선호 태그는 검색
 * 키워드 빈도가 source가 된다 (사용자 자기 발화 = 가장 명확한 선호 표현).
 *
 * 칭호는 behaviorTracking 이벤트 + 검색 이력에서 계산. 5/29 합의 5 카테고리
 * 29종. badges.js의 getEarnedBadges가 한 줄로 다 처리. CLAUDE.md §5.13 (8).
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
  getPreferredTags,
  clearAllUserData,
} from '../services/userStorageService';
import { getBehaviorEvents, clearBehaviorEvents } from '../services/behaviorTrackingService';
import { getEarnedBadges } from '../services/badges';
import { getCurrentUser, logout } from '../services/authService';
import {
  getSimilarUsers,
  getUserEvents,
  getUserDiary,
  clearServerUserData,
} from '../services/recommendationService';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

/**
 * 미식 유형 8종 — Backend seed_demo.py TYPES 와 동일한 시드 쌍.
 * 상위 시드 2개로 사용자를 가장 가까운 유형에 매칭한다.
 */
const PERSONA_TYPES = [
  { id: 'T1', name: '매운국물파', emoji: '🌶️', seeds: ['얼큰한', '국물있는'] },
  { id: 'T2', name: '튀김전러버', emoji: '🍗', seeds: ['고소한', '바삭한'] },
  { id: 'T3', name: '뜨끈보양파', emoji: '🍲', seeds: ['국물있는', '든든한'] },
  { id: 'T4', name: '진한메인파', emoji: '🥩', seeds: ['든든한', '진한'] },
  { id: 'T5', name: '단짠간식파', emoji: '🍰', seeds: ['달달한', '바삭한'] },
  { id: 'T6', name: '해장파', emoji: '🍜', seeds: ['국물있는', '해장'] },
  { id: 'T7', name: '슴슴든든파', emoji: '🍚', seeds: ['담백한', '든든한'] },
  { id: 'T8', name: '따뜻집밥파', emoji: '🏠', seeds: ['든든한', '따뜻한'] },
];

/**
 * 검색 키워드 빈도(preferredTags) + 최종선택 음식 태그(seedCounts)를 합산해
 * 시드별 점수 맵을 만든다. 검색만 한 게스트도, 선택까지 한 사용자도 모두 반영.
 */
function buildSeedScore(preferredTags = [], seedCounts = {}) {
  const score = {};
  preferredTags.forEach(({ tag, count }) => {
    score[tag] = (score[tag] || 0) + count;
  });
  Object.entries(seedCounts).forEach(([tag, count]) => {
    score[tag] = (score[tag] || 0) + count;
  });
  return score;
}

/** 시드 점수 맵 → 상위 N개 [{tag, score, pct, rel}] (pct=전체 비중, rel=최댓값 대비). */
function topSeeds(seedScore, n = 5) {
  const entries = Object.entries(seedScore)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return [];
  const total = entries.reduce((s, [, v]) => s + v, 0);
  const max = entries[0][1];
  return entries.slice(0, n).map(([tag, v]) => ({
    tag,
    score: v,
    pct: Math.round((v / total) * 100),
    rel: v / max,
  }));
}

/** 시드 점수 맵 → 가장 가까운 미식 유형 (데이터 없으면 null). */
function diagnosePersona(seedScore) {
  let best = null;
  let bestScore = 0;
  for (const type of PERSONA_TYPES) {
    const s = type.seeds.reduce((acc, seed) => acc + (seedScore[seed] || 0), 0);
    if (s > bestScore) {
      bestScore = s;
      best = type;
    }
  }
  return bestScore > 0 ? best : null;
}

export default function MyPageScreen({ navigation }) {
  const [searches, setSearches] = useState([]);
  const [preferredTags, setPreferredTags] = useState([]);
  const [badges, setBadges] = useState({ earned: [], all: [], stats: {} });
  const [account, setAccount] = useState(null); // 로그인 유저(없으면 비로그인)
  const [similarUsers, setSimilarUsers] = useState([]); // CF 닮은 사용자 (서버)
  const [diary, setDiary] = useState([]); // 나의 먹거리 일기 (서버 DB, user_id별)
  const [diaryOpen, setDiaryOpen] = useState(false); // 접이식 — 버튼 누르면 펼침

  // 화면이 포커스될 때마다 데이터 새로 불러오기 (검색·식당 이동 후 즉시 반영)
  useFocusEffect(
    useCallback(() => {
      let mounted = true;
      (async () => {
        const [s, u] = await Promise.all([
          getRecentSearches(),
          getCurrentUser(),
        ]);
        if (!mounted) return;
        setSearches(s); // '나의 먹거리 일기' — 이 기기 검색 이력(쿼리+태그+추천메뉴)
        setAccount(u);

        // 칭호·미식유형·닮은사용자 = *서버 user_id 기준* (계정 바꾸면 달라짐).
        // 로그인 유저 또는 비로그인=1(Alice).
        const uid = u?.user_id ?? 1;
        // 서버 행동 데이터로 칭호·미식유형 계산. 실패 시 로컬 AsyncStorage 폴백.
        const ue = await getUserEvents(uid);
        let evList, searchList, prefTags;
        if (ue) {
          evList = ue.events;
          searchList = ue.searches;
          prefTags = ue.preferredTags;
        } else {
          [evList, searchList, prefTags] = await Promise.all([
            getBehaviorEvents(),
            Promise.resolve(s),
            getPreferredTags(),
          ]);
        }
        if (!mounted) return;
        setPreferredTags(prefTags); // 미식유형 seedScore에 사용
        setBadges(getEarnedBadges(evList, searchList));

        const sims = await getSimilarUsers(uid);
        if (mounted) setSimilarUsers(sims);
        // 나의 먹거리 일기 — 서버 DB의 그 user_id 태그검색·선택 이력
        const dia = await getUserDiary(uid);
        if (mounted) setDiary(dia);
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
      '검색 이력, 추천 이력, 행동 이벤트, 칭호가 모두 초기화됩니다.',
      [
        { text: '취소', style: 'cancel' },
        {
          text: '삭제',
          style: 'destructive',
          onPress: async () => {
            const uid = account?.user_id ?? 1;
            await clearAllUserData();
            await clearBehaviorEvents();
            const serverCleared = await clearServerUserData(uid);
            setSearches([]);
            setPreferredTags([]);
            setBadges({ earned: [], all: [], stats: {} });
            setSimilarUsers([]);
            setDiary([]);
            setDiaryOpen(false);
            if (!serverCleared) {
              Alert.alert(
                '서버 기록 삭제 실패',
                '이 기기의 기록은 지웠지만 서버 기록은 다시 보일 수 있습니다.'
              );
            }
          },
        },
      ]
    );
  };

  // 로그아웃 — 토큰 삭제 후 로그인 화면으로 (스택 리셋)
  const handleLogout = () => {
    Alert.alert('로그아웃 할까요?', '다시 이용하려면 로그인이 필요해요.', [
      { text: '취소', style: 'cancel' },
      {
        text: '로그아웃',
        style: 'destructive',
        onPress: async () => {
          await logout();
          navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
        },
      },
    ]);
  };

  // 로그인 화면으로 이동(비로그인 상태에서)
  const goLogin = () => navigation.reset({ index: 0, routes: [{ name: 'Login' }] });

  // 빈 상태 — 로컬 데이터·칭호·닮은 사용자 모두 0일 때만
  // (닮은 사용자는 서버 CF라 로컬 기록 0인 게스트도 채워질 수 있음)
  const isEmpty =
    searches.length === 0 &&
    diary.length === 0 &&
    badges.earned.length === 0 &&
    similarUsers.length === 0;

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
        {/* 계정 카드 */}
        <View style={styles.accountCard}>
          {account ? (
            <>
              <View style={styles.accountInfo}>
                <Text style={styles.accountAvatar}>👤</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.accountEmail} numberOfLines={1}>
                    {account.email}
                  </Text>
                  <Text style={styles.accountStatus}>로그인됨</Text>
                </View>
              </View>
              <Pressable
                onPress={handleLogout}
                hitSlop={8}
                style={({ pressed }) => [styles.logoutBtn, pressed && { opacity: 0.7 }]}
              >
                <Text style={styles.logoutText}>로그아웃</Text>
              </Pressable>
            </>
          ) : (
            <>
              <View style={styles.accountInfo}>
                <Text style={styles.accountAvatar}>🙋</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.accountEmail}>로그인하지 않았어요</Text>
                  <Text style={styles.accountStatus}>로그인하면 기기 간 기록을 이어갈 수 있어요</Text>
                </View>
              </View>
              <Pressable
                onPress={goLogin}
                hitSlop={8}
                style={({ pressed }) => [styles.loginBtn, pressed && { opacity: 0.85 }]}
              >
                <Text style={styles.loginBtnText}>로그인</Text>
              </Pressable>
            </>
          )}
        </View>

        {isEmpty && (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyEmoji}>🍽️</Text>
            <Text style={styles.emptyTitle}>아직 기록이 없어요</Text>
            <Text style={styles.emptyDesc}>
              메뉴를 검색하고 식당 길찾기를 눌러보세요.{'\n'}
              사용할수록 칭호를 모을 수 있어요.
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

        {/* 0. 취향 프로필 카드 — 미식 유형 진단 + 시드 분포 + 칭호 + 통계 */}
        {!isEmpty && (
          <TasteProfileCard
            badges={badges}
            searchCount={searches.length}
            preferredTags={preferredTags}
          />
        )}

        {/* 0.5 나와 닮은 사용자 (CF) — 서버 데이터라 로컬 기록과 독립 */}
        {!isEmpty && similarUsers.length > 0 && (
          <Section
            title="나와 닮은 사용자"
            subtitle={`취향이 비슷한 ${similarUsers.length}명`}
            icon="🤝"
          >
            {similarUsers.map((u) => (
              <View key={u.userId} style={styles.simUserRow}>
                <Text style={styles.simAvatar}>👤</Text>
                <View style={styles.simInfo}>
                  <View style={styles.simNameRow}>
                    <Text style={styles.simName} numberOfLines={1}>
                      {u.name}
                    </Text>
                    <Text style={styles.simMatch}>{u.match}% 일치</Text>
                  </View>
                  {u.sharedFoods && u.sharedFoods.length > 0 && (
                    <Text style={styles.simShared} numberOfLines={1}>
                      둘 다 고른: {u.sharedFoods.join(' · ')}
                    </Text>
                  )}
                </View>
              </View>
            ))}
            <Text style={styles.simNote}>
              💡 이들이 고른 메뉴가 "나를 위한 추천(CF)"에 반영돼요
            </Text>
          </Section>
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

        {/* 2. 칭호 도감 — 5 카테고리 29종 (CLAUDE.md §5.13 (8)) */}
        {!isEmpty && badges.all.length > 0 && <BadgeCatalog badges={badges} />}

        {/* 3. 나의 먹거리 일기 — 서버 DB(user_id별) 태그검색·선택 이력. 버튼 누르면 펼침 */}
        {!isEmpty && diary.length > 0 && (
          <View style={styles.section}>
            <Pressable
              onPress={() => setDiaryOpen((o) => !o)}
              style={({ pressed }) => [styles.diaryToggle, pressed && { opacity: 0.7 }]}
            >
              <Text style={styles.sectionIcon}>📖</Text>
              <Text style={styles.sectionTitle}>나의 먹거리 일기</Text>
              <View style={{ flex: 1 }} />
              <Text style={styles.diaryCount}>{diary.length}개</Text>
              <Text style={styles.diaryChevron}>{diaryOpen ? '▾' : '▸'}</Text>
            </Pressable>

            {diaryOpen &&
              diary.map((e) => (
                <View key={e.sessionId} style={styles.diaryEntry}>
                  <View style={styles.diaryHeader}>
                    <View style={styles.diaryTags}>
                      {(e.tags || []).map((t, i) => (
                        <Text key={i} style={styles.searchKeyword}>
                          #{t}
                        </Text>
                      ))}
                    </View>
                    <Text style={styles.searchTime}>
                      {formatRelativeTime(new Date(e.timestamp).getTime())}
                    </Text>
                  </View>
                  {e.selected && e.selected.length > 0 && (
                    <View style={styles.diarySelectedBox}>
                      <Text style={styles.diarySelectedLabel}>선택한 메뉴</Text>
                      <Text style={styles.diarySelectedNames} numberOfLines={2}>
                        {e.selected.join(' · ')}
                      </Text>
                    </View>
                  )}
                  {e.clicked && e.clicked.length > 0 && (
                    <Text style={styles.diaryClicked} numberOfLines={2}>
                      👆 클릭 {e.clicked.join(' · ')}
                    </Text>
                  )}
                </View>
              ))}
          </View>
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
/**
 * 취향 프로필 카드 — 상단 hero
 *
 * 달성한 칭호 1~4개를 가장 눈에 띄게 노출.
 * 메인 칭호(카테고리 A~D)에서 우선 1~3개, 메타(E)에서 0~1개.
 */
function TasteProfileCard({ badges, searchCount, preferredTags = [] }) {
  const earnedMain = badges.earned.filter((b) => b.category !== 'E').slice(0, 3);
  const earnedMeta = badges.earned.filter((b) => b.category === 'E').slice(0, 1);
  const chips = [...earnedMain, ...earnedMeta];

  const stats = badges.stats || {};

  // 미식 유형 진단 + 시드 분포 (검색 키워드 + 최종선택 음식 태그 합산)
  const seedScore = buildSeedScore(preferredTags, stats.seedCounts || {});
  const persona = diagnosePersona(seedScore);
  const bars = topSeeds(seedScore, 5);

  const stat = (label, value) => (
    <View style={styles.statItem}>
      <Text style={styles.statNum}>{value ?? 0}</Text>
      <Text style={styles.statName}>{label}</Text>
    </View>
  );

  return (
    <View style={styles.profileCard}>
      <View style={styles.profileLabelRow}>
        <View style={styles.profileDot} />
        <Text style={styles.profileLabel}>YOUR TASTE</Text>
      </View>

      {/* 미식 유형 진단 (hero) */}
      {persona ? (
        <View style={styles.personaRow}>
          <Text style={styles.personaEmoji}>{persona.emoji}</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.personaName}>{persona.name}</Text>
            <Text style={styles.personaSeeds}>
              {persona.seeds.join(' · ')} 선호
            </Text>
          </View>
        </View>
      ) : (
        <Text style={styles.profileEmpty}>
          메뉴를 검색하면 당신의 미식 유형이 나와요
        </Text>
      )}

      {/* 시드 분포 막대 */}
      {bars.length > 0 && (
        <View style={styles.seedBars}>
          {bars.map((b) => (
            <View key={b.tag} style={styles.seedBarRow}>
              <Text style={styles.seedBarLabel} numberOfLines={1}>
                {b.tag}
              </Text>
              <View style={styles.seedBarTrack}>
                <View
                  style={[styles.seedBarFill, { width: `${Math.max(8, b.rel * 100)}%` }]}
                />
              </View>
              <Text style={styles.seedBarPct}>{b.pct}%</Text>
            </View>
          ))}
        </View>
      )}

      {/* 달성 칭호 칩 */}
      {chips.length > 0 && (
        <View style={styles.profileChipWrap}>
          {chips.map((b) => (
            <View key={b.id} style={styles.profileChip}>
              <Text style={styles.profileChipIcon}>{b.icon}</Text>
              <Text style={styles.profileChipName}>{b.name}</Text>
            </View>
          ))}
        </View>
      )}

      <View style={styles.statRow}>
        {stat('받은 칭호', badges.earned.length)}
        {stat('시도 종류', Object.keys(stats.kindCounts || {}).length)}
        {stat('가본 식당', (stats.finalCount || 0) > 0 ? Object.keys((stats.kindCounts || {})).length : 0)}
        {stat('검색', searchCount)}
      </View>
    </View>
  );
}

/**
 * 칭호 도감 — 5 카테고리 29종 그리드.
 * 달성=풀컬러, 미달성=회색 + 진행률 안내.
 */
function BadgeCatalog({ badges }) {
  const [selectedCategory, setSelectedCategory] = useState('A');
  const total = badges.all.length;
  const earned = badges.earned.length;

  // 카테고리 라벨
  const CATEGORY_LABELS = {
    A: '맛 속성', B: '장르', C: '음식', D: '행동 패턴', E: '메타',
  };
  const groups = ['A', 'B', 'C', 'D', 'E'].map((cat) => ({
    cat,
    label: CATEGORY_LABELS[cat],
    items: badges.all.filter((b) => b.category === cat),
  }));
  const selectedGroup = groups.find((g) => g.cat === selectedCategory) || groups[0];

  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionIcon}>📜</Text>
        <Text style={styles.sectionTitle}>칭호 도감</Text>
        <Text style={styles.sectionSub}>· {earned} / {total}</Text>
      </View>
      <View style={styles.badgeCategoryTabs}>
        {groups.map((g) => {
          const isActive = selectedCategory === g.cat;
          const earnedCount = g.items.filter((b) => b.earned).length;
          return (
            <Pressable
              key={g.cat}
              onPress={() => setSelectedCategory(g.cat)}
              style={({ pressed }) => [
                styles.badgeCategoryTab,
                isActive && styles.badgeCategoryTabActive,
                pressed && styles.badgeCategoryTabPressed,
              ]}
            >
              <Text style={[styles.badgeCategoryTabCode, isActive && styles.badgeCategoryTabCodeActive]}>
                {g.cat}
              </Text>
              <Text
                style={[styles.badgeCategoryTabLabel, isActive && styles.badgeCategoryTabLabelActive]}
                numberOfLines={2}
              >
                {g.label}
              </Text>
              <Text style={[styles.badgeCategoryTabCount, isActive && styles.badgeCategoryTabCountActive]}>
                {earnedCount}/{g.items.length}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.badgeCategoryBlock}>
        <Text style={styles.badgeCategoryLabel}>
          {selectedGroup.cat}. {selectedGroup.label}  <Text style={styles.badgeCategoryCount}>
            {selectedGroup.items.filter((b) => b.earned).length}/{selectedGroup.items.length}
          </Text>
        </Text>
        <View style={styles.badgeGrid}>
          {selectedGroup.items.map((b) => (
            <BadgeCell key={b.id} badge={b} />
          ))}
        </View>
      </View>
    </View>
  );
}

function BadgeCell({ badge }) {
  const earned = badge.earned;
  const progress = badge.progress;
  const pct = progress && progress.target
    ? Math.min(1, (progress.current || 0) / progress.target)
    : 0;

  return (
    <View style={[styles.badgeCell, !earned && styles.badgeCellLocked]}>
      <Text style={[styles.badgeIcon, !earned && styles.badgeIconLocked]}>
        {badge.icon}
      </Text>
      <Text
        style={[styles.badgeName, !earned && styles.badgeNameLocked]}
        numberOfLines={2}
      >
        {badge.name}
      </Text>
      {!earned && progress && progress.target ? (
        <>
          <View style={styles.badgeProgressBar}>
            <View
              style={[
                styles.badgeProgressFill,
                { width: `${pct * 100}%` },
              ]}
            />
          </View>
          <Text style={styles.badgeProgressText}>
            {progress.current || 0}/{progress.target}
          </Text>
        </>
      ) : null}
    </View>
  );
}

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

  // === 계정 카드 ===
  accountCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: SPACING.md,
    marginTop: SPACING.sm,
  },
  accountInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: SPACING.md,
  },
  accountAvatar: {
    fontSize: 26,
    marginRight: SPACING.md,
  },
  accountEmail: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
    marginBottom: 2,
  },
  accountStatus: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
  },
  logoutBtn: {
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  logoutText: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightMedium,
  },
  loginBtn: {
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.sm,
    borderRadius: RADIUS.md,
    backgroundColor: COLORS.primary,
  },
  loginBtnText: {
    color: '#1A0F08',
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightBold,
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

  // === 취향 프로필 카드 (TasteProfileCard) ===
  profileCard: {
    backgroundColor: COLORS.surfaceAlt,
    borderColor: COLORS.primary,
    borderWidth: 1,
    borderRadius: RADIUS.xl,
    padding: SPACING.lg,
    marginBottom: SPACING.lg,
  },
  profileLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  profileDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: COLORS.primary,
    marginRight: SPACING.sm,
  },
  profileLabel: {
    fontSize: 11,
    fontWeight: FONT.weightBold,
    color: COLORS.accent,
    letterSpacing: 1.5,
  },
  // === 미식 유형 진단 (hero) ===
  personaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: SPACING.xs,
    marginBottom: SPACING.md,
  },
  personaEmoji: {
    fontSize: 36,
    marginRight: SPACING.md,
  },
  personaName: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeLg,
    fontWeight: FONT.weightExtra,
    marginBottom: 2,
  },
  personaSeeds: {
    color: COLORS.accent,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightMedium,
  },

  // === 시드 분포 막대 ===
  seedBars: {
    marginBottom: SPACING.md,
    gap: 6,
  },
  seedBarRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  seedBarLabel: {
    width: 56,
    color: COLORS.textSecondary,
    fontSize: 11,
    fontWeight: FONT.weightMedium,
  },
  seedBarTrack: {
    flex: 1,
    height: 8,
    backgroundColor: COLORS.bg,
    borderRadius: 4,
    overflow: 'hidden',
    marginHorizontal: SPACING.sm,
  },
  seedBarFill: {
    height: '100%',
    backgroundColor: COLORS.primary,
    borderRadius: 4,
  },
  seedBarPct: {
    width: 34,
    textAlign: 'right',
    color: COLORS.textMuted,
    fontSize: 11,
    fontWeight: FONT.weightBold,
  },

  // === 나와 닮은 사용자 (CF) ===
  simUserRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: SPACING.sm,
  },
  simAvatar: {
    fontSize: 22,
    marginRight: SPACING.md,
  },
  simInfo: {
    flex: 1,
  },
  simNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  simName: {
    flex: 1,
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
    marginRight: SPACING.sm,
  },
  simMatch: {
    color: COLORS.primary,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightExtra,
  },
  simShared: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
    marginTop: 2,
  },
  simNote: {
    color: COLORS.accent,
    fontSize: FONT.sizeXs,
    marginTop: SPACING.xs,
    lineHeight: 17,
  },

  profileChipWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: SPACING.sm,
    marginTop: SPACING.xs,
    marginBottom: SPACING.md,
  },
  profileChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bg,
    borderColor: COLORS.primary,
    borderWidth: 1,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    borderRadius: RADIUS.pill,
  },
  profileChipIcon: {
    fontSize: 16,
    marginRight: 6,
  },
  profileChipName: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
  },
  profileEmpty: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    lineHeight: 20,
    marginTop: SPACING.sm,
    marginBottom: SPACING.md,
  },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: SPACING.md,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
  },
  statItem: {
    alignItems: 'center',
    flex: 1,
  },
  statNum: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightExtra,
  },
  statName: {
    color: COLORS.textMuted,
    fontSize: 11,
    marginTop: 2,
  },

  // === 칭호 도감 (BadgeCatalog) ===
  badgeCategoryTabs: {
    flexDirection: 'row',
    gap: SPACING.sm,
    marginBottom: SPACING.sm,
  },
  badgeCategoryTab: {
    flex: 1,
    minHeight: 44,
    backgroundColor: COLORS.bg,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingVertical: 6,
    paddingHorizontal: 4,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeCategoryTabActive: {
    backgroundColor: COLORS.primarySoft,
    borderColor: COLORS.primary,
  },
  badgeCategoryTabPressed: {
    opacity: 0.75,
  },
  badgeCategoryTabCode: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightExtra,
  },
  badgeCategoryTabCodeActive: {
    color: COLORS.primary,
  },
  badgeCategoryTabLabel: {
    color: COLORS.textSecondary,
    fontSize: 9,
    fontWeight: FONT.weightBold,
    textAlign: 'center',
    marginTop: 1,
  },
  badgeCategoryTabLabelActive: {
    color: COLORS.textPrimary,
  },
  badgeCategoryTabCount: {
    color: COLORS.textMuted,
    fontSize: 9,
    marginTop: 1,
    textAlign: 'center',
  },
  badgeCategoryTabCountActive: {
    color: COLORS.primary,
    fontWeight: FONT.weightBold,
  },
  badgeCategoryBlock: {
    marginBottom: SPACING.md,
  },
  badgeCategoryLabel: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
    marginBottom: SPACING.sm,
  },
  badgeCategoryCount: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
    fontWeight: FONT.weightRegular,
  },
  badgeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: SPACING.sm,
  },
  badgeCell: {
    width: '23%',
    aspectRatio: 0.75,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.primary,
    padding: SPACING.xs,
    alignItems: 'center',
    justifyContent: 'flex-start',
  },
  badgeCellLocked: {
    borderColor: COLORS.border,
    backgroundColor: COLORS.bg,
    opacity: 0.7,
  },
  badgeIcon: {
    fontSize: 24,
    marginTop: 4,
    marginBottom: 4,
  },
  badgeIconLocked: {
    opacity: 0.4,
  },
  badgeName: {
    color: COLORS.textPrimary,
    fontSize: 10,
    fontWeight: FONT.weightBold,
    textAlign: 'center',
    lineHeight: 13,
  },
  badgeNameLocked: {
    color: COLORS.textMuted,
  },
  badgeProgressBar: {
    height: 3,
    backgroundColor: COLORS.border,
    borderRadius: 2,
    width: '85%',
    marginTop: 4,
    overflow: 'hidden',
  },
  badgeProgressFill: {
    height: '100%',
    backgroundColor: COLORS.accent,
  },
  badgeProgressText: {
    color: COLORS.textMuted,
    fontSize: 9,
    marginTop: 2,
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
    flex: 1,
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontStyle: 'italic',
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
  // 나의 먹거리 일기 — 접이식 버튼 + 한 칸: 태그 + 선택/클릭 음식
  diaryToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  diaryCount: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
    marginRight: SPACING.xs,
  },
  diaryChevron: {
    color: COLORS.primary,
    fontSize: FONT.sizeMd,
  },
  diaryEntry: {
    backgroundColor: COLORS.surface,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: SPACING.sm,
  },
  diaryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  diaryTags: {
    flex: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  diarySelectedBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.primarySoft,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.primary,
    padding: SPACING.sm,
    marginTop: SPACING.xs,
  },
  diarySelectedLabel: {
    color: COLORS.primary,
    fontSize: 10,
    fontWeight: FONT.weightBold,
    marginRight: SPACING.sm,
  },
  diarySelectedNames: {
    flex: 1,
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
  },
  diaryClicked: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    marginTop: 4,
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
