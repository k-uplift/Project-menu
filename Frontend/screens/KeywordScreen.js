/**
 * KeywordScreen — 키워드 확인 + 컨텍스트 설정 (STEP 02)
 *
 * 추가된 영역:
 *  1. 자동 감지 정보 (현재 시간 / 현재 날씨)
 *  2. 추가 조건 토글 (국물 / 인원 / 칼로리)
 *  3. 가중치 슬라이더 (날씨 / 시간대 / 취향)
 *
 * 단, 사용자가 손대지 않으면 그냥 자동 컨텍스트만 적용됨 → 기본 흐름 단순함 유지
 */

import React, { useState, useMemo, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  Pressable,
  Alert,
} from 'react-native';

import ScreenContainer from '../components/ScreenContainer';
import PrimaryButton from '../components/PrimaryButton';
import KeywordTag from '../components/KeywordTag';
import WeightSlider from '../components/WeightSlider';
import { createUserKeyword } from '../services/keywordService';
import {
  getCurrentTimeContext,
  getCurrentWeather,
} from '../services/contextService';
import { SUGGESTED_KEYWORDS } from '../constants/config';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function KeywordScreen({ route, navigation }) {
  const { analyzeResult } = route.params;

  // 키워드 상태
  const [keywords, setKeywords] = useState(
    (analyzeResult.keywords || []).map((k) => ({ ...k, selected: true }))
  );
  const [newKeyword, setNewKeyword] = useState('');

  // 자동 감지 컨텍스트
  const [timeCtx] = useState(() => getCurrentTimeContext());
  const [weatherCtx, setWeatherCtx] = useState(null);

  // 사용자 설정 컨텍스트
  const [conditions, setConditions] = useState({
    soup: null,        // 'yes' | 'no' | 'any' | null
    people: null,      // 'solo' | '2' | '3+' | null
    calorie: null,     // 'low' | 'mid' | 'high' | null
  });
  const [weights, setWeights] = useState({
    weather: 50,
    time: 50,
    taste: 70,
  });

  // 컨텍스트 설정 영역 펼침/접힘
  const [showContext, setShowContext] = useState(false);

  // 날씨 자동 로드
  useEffect(() => {
    let mounted = true;
    (async () => {
      const w = await getCurrentWeather();
      if (mounted) setWeatherCtx(w);
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const selectedCount = useMemo(
    () => keywords.filter((k) => k.selected).length,
    [keywords]
  );

  const toggleKeyword = (id) => {
    setKeywords((prev) =>
      prev.map((k) => (k.id === id ? { ...k, selected: !k.selected } : k))
    );
  };

  const handleAddKeyword = (label) => {
    const trimmed = label.trim();
    if (trimmed.length === 0) return;
    if (trimmed.length > 12) {
      Alert.alert('너무 길어요', '12글자 이내로 입력해주세요.');
      return;
    }
    if (keywords.some((k) => k.label === trimmed)) {
      Alert.alert('이미 추가됨', '같은 키워드가 이미 있어요.');
      return;
    }
    const newKw = createUserKeyword(trimmed);
    setKeywords((prev) => [...prev, { ...newKw, selected: true }]);
    setNewKeyword('');
  };

  const handleNext = () => {
    const selected = keywords.filter((k) => k.selected);
    if (selected.length === 0) {
      Alert.alert('키워드를 선택해주세요', '최소 1개 이상 선택해야 추천을 받을 수 있어요.');
      return;
    }
    navigation.navigate('Recommend', {
      keywords: selected,
      originalText: analyzeResult.originalText,
      context: { timeCtx, weatherCtx, conditions, weights },
    });
  };

  const usedLabels = new Set(keywords.map((k) => k.label));
  const suggestions = SUGGESTED_KEYWORDS.filter((s) => !usedLabels.has(s));

  return (
    <ScreenContainer
      step="keyword"
      bottomBar={
        <View style={styles.bottomBarRow}>
          <View style={{ flex: 1 }}>
            <PrimaryButton
              label="다시 입력"
              variant="ghost"
              onPress={() => navigation.popToTop()}
            />
          </View>
          <View style={{ width: SPACING.sm }} />
          <View style={{ flex: 1.4 }}>
            <PrimaryButton
              label={`${selectedCount}개로 추천받기 →`}
              onPress={handleNext}
              disabled={selectedCount === 0}
            />
          </View>
        </View>
      }
    >
      <Text style={styles.title}>이 키워드가 맞나요?</Text>
      <Text style={styles.sub}>
        탭해서 제거하거나, 직접 추가할 수도 있어요.{'\n'}
        같은 표현이라도 사람마다 의미가 다를 수 있으니까요.
      </Text>

      {/* 입력 원문 미리보기 */}
      <View style={styles.previewBox}>
        <Text style={styles.previewLabel}>입력한 내용</Text>
        <Text style={styles.previewText}>"{analyzeResult.originalText}"</Text>
      </View>

      {/* AI 추출 키워드 */}
      <Text style={styles.sectionLabel}>AI가 뽑은 키워드</Text>
      <View style={styles.tagWrap}>
        {keywords.map((kw) => (
          <KeywordTag
            key={kw.id}
            label={kw.label}
            selected={kw.selected}
            onPress={() => toggleKeyword(kw.id)}
            showRemove={kw.selected}
          />
        ))}
        {keywords.length === 0 && (
          <Text style={styles.empty}>키워드를 추출하지 못했어요. 직접 추가해보세요.</Text>
        )}
      </View>

      {/* 직접 추가 */}
      <Text style={styles.sectionLabel}>키워드 직접 추가</Text>
      <View style={styles.addRow}>
        <TextInput
          value={newKeyword}
          onChangeText={setNewKeyword}
          placeholder="원하는 키워드 입력"
          placeholderTextColor={COLORS.textMuted}
          style={styles.addInput}
          maxLength={12}
          onSubmitEditing={() => handleAddKeyword(newKeyword)}
          returnKeyType="done"
        />
        <Pressable
          onPress={() => handleAddKeyword(newKeyword)}
          disabled={newKeyword.trim().length === 0}
          style={({ pressed }) => [
            styles.addBtn,
            newKeyword.trim().length === 0 && styles.addBtnDisabled,
            pressed && styles.addBtnPressed,
          ]}
        >
          <Text style={styles.addBtnText}>추가</Text>
        </Pressable>
      </View>

      {/* 추천 키워드 */}
      {suggestions.length > 0 && (
        <>
          <Text style={[styles.sectionLabel, { marginTop: SPACING.lg }]}>
            이런 키워드는 어떠세요?
          </Text>
          <View style={styles.tagWrap}>
            {suggestions.slice(0, 8).map((s) => (
              <KeywordTag
                key={s}
                label={s}
                variant="add"
                onPress={() => handleAddKeyword(s)}
              />
            ))}
          </View>
        </>
      )}

      {/* ============================================
          컨텍스트 설정 영역 (접힘/펼침 가능)
         ============================================ */}
      <View style={styles.contextSection}>
        {/* 자동 감지 정보 — 항상 표시 */}
        <View style={styles.autoCtxRow}>
          <AutoCtxCard
            label="현재 시간"
            value={timeCtx.displayText}
          />
          <AutoCtxCard
            label="현재 날씨"
            value={weatherCtx ? weatherCtx.displayText : '확인 중...'}
            emoji={weatherCtx?.emoji}
          />
        </View>

        {/* 펼치기 토글 */}
        <Pressable
          onPress={() => setShowContext(!showContext)}
          style={({ pressed }) => [
            styles.expandBtn,
            pressed && styles.expandBtnPressed,
          ]}
        >
          <Text style={styles.expandText}>
            추천 조건 직접 설정하기 (선택)
          </Text>
          <Text style={styles.expandArrow}>{showContext ? '⌃' : '⌄'}</Text>
        </Pressable>

        {showContext && (
          <View style={styles.expandedBox}>
            {/* 3-Way 토글: 국물 */}
            <ToggleRow
              label="국물"
              options={[
                { key: 'yes', label: '있음' },
                { key: 'no', label: '없음' },
                { key: 'any', label: '상관없음' },
              ]}
              value={conditions.soup}
              onChange={(v) => setConditions({ ...conditions, soup: v })}
            />

            <ToggleRow
              label="인원"
              options={[
                { key: 'solo', label: '혼밥' },
                { key: '2', label: '2인' },
                { key: '3+', label: '3인+' },
              ]}
              value={conditions.people}
              onChange={(v) => setConditions({ ...conditions, people: v })}
            />

            <ToggleRow
              label="칼로리"
              options={[
                { key: 'low', label: '적게' },
                { key: 'mid', label: '보통' },
                { key: 'high', label: '많이' },
              ]}
              value={conditions.calorie}
              onChange={(v) => setConditions({ ...conditions, calorie: v })}
            />

            <View style={styles.divider} />

            {/* 컨텍스트 가중치 슬라이더 */}
            <Text style={styles.weightSectionTitle}>컨텍스트 가중치</Text>

            <WeightSlider
              label="날씨 영향도"
              value={weights.weather}
              onChange={(v) => setWeights({ ...weights, weather: v })}
            />
            <WeightSlider
              label="시간대 영향도"
              value={weights.time}
              onChange={(v) => setWeights({ ...weights, time: v })}
            />
            <WeightSlider
              label="개인 취향 반영"
              value={weights.taste}
              onChange={(v) => setWeights({ ...weights, taste: v })}
            />
          </View>
        )}
      </View>

      <Text style={styles.note}>
        💡 선택된 키워드만 추천에 반영돼요
      </Text>
    </ScreenContainer>
  );
}

/** 자동 감지 정보 카드 */
function AutoCtxCard({ label, value, emoji }) {
  return (
    <View style={styles.autoCtxCard}>
      <Text style={styles.autoCtxLabel}>{label}</Text>
      <View style={styles.autoCtxValueRow}>
        {emoji && <Text style={styles.autoCtxEmoji}>{emoji}</Text>}
        <Text style={styles.autoCtxValue}>{value}</Text>
      </View>
    </View>
  );
}

/** 3-Way 토글 행 */
function ToggleRow({ label, options, value, onChange }) {
  return (
    <View style={styles.toggleRow}>
      <Text style={styles.toggleLabel}>{label}</Text>
      <View style={styles.toggleOptions}>
        {options.map((opt) => {
          const isActive = value === opt.key;
          return (
            <Pressable
              key={opt.key}
              onPress={() => onChange(isActive ? null : opt.key)}
              style={({ pressed }) => [
                styles.toggleBtn,
                isActive && styles.toggleBtnActive,
                pressed && styles.toggleBtnPressed,
              ]}
            >
              <Text style={[
                styles.toggleBtnText,
                isActive && styles.toggleBtnTextActive,
              ]}>
                {opt.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  title: {
    fontSize: FONT.sizeXl,
    fontWeight: FONT.weightExtra,
    color: COLORS.textPrimary,
    marginTop: SPACING.md,
    marginBottom: SPACING.sm,
  },
  sub: {
    fontSize: FONT.sizeSm,
    color: COLORS.textSecondary,
    lineHeight: 20,
    marginBottom: SPACING.lg,
  },

  previewBox: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    borderLeftWidth: 3,
    borderLeftColor: COLORS.primary,
    marginBottom: SPACING.xl,
  },
  previewLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginBottom: 4,
  },
  previewText: {
    fontSize: FONT.sizeSm,
    color: COLORS.textPrimary,
    fontStyle: 'italic',
    lineHeight: 20,
  },

  sectionLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: SPACING.sm,
    fontWeight: FONT.weightBold,
  },

  tagWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: SPACING.sm,
    marginBottom: SPACING.lg,
  },
  empty: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeSm,
    fontStyle: 'italic',
  },

  addRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    marginBottom: SPACING.md,
  },
  addInput: {
    flex: 1,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.md,
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginRight: SPACING.sm,
  },
  addBtn: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: SPACING.lg,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addBtnDisabled: {
    opacity: 0.4,
  },
  addBtnPressed: {
    opacity: 0.85,
  },
  addBtnText: {
    color: '#1A0F08',
    fontWeight: FONT.weightBold,
    fontSize: FONT.sizeSm,
  },

  // === 컨텍스트 영역 ===
  contextSection: {
    marginTop: SPACING.lg,
    paddingTop: SPACING.lg,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
  },
  autoCtxRow: {
    flexDirection: 'row',
    gap: SPACING.sm,
    marginBottom: SPACING.md,
  },
  autoCtxCard: {
    flex: 1,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  autoCtxLabel: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginBottom: 4,
  },
  autoCtxValueRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  autoCtxEmoji: {
    fontSize: 14,
    marginRight: 4,
  },
  autoCtxValue: {
    fontSize: FONT.sizeSm,
    color: COLORS.textPrimary,
    fontWeight: FONT.weightBold,
  },

  expandBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: SPACING.md,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderStyle: 'dashed',
  },
  expandBtnPressed: {
    backgroundColor: COLORS.surfaceAlt,
  },
  expandText: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightMedium,
    marginRight: SPACING.sm,
  },
  expandArrow: {
    color: COLORS.primary,
    fontSize: FONT.sizeMd,
    fontWeight: FONT.weightExtra,
  },

  expandedBox: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    padding: SPACING.lg,
    marginTop: SPACING.sm,
    borderWidth: 1,
    borderColor: COLORS.border,
  },

  toggleRow: {
    marginBottom: SPACING.md,
  },
  toggleLabel: {
    fontSize: FONT.sizeSm,
    color: COLORS.textSecondary,
    marginBottom: SPACING.sm,
  },
  toggleOptions: {
    flexDirection: 'row',
    gap: SPACING.sm,
  },
  toggleBtn: {
    flex: 1,
    paddingVertical: SPACING.sm,
    backgroundColor: COLORS.bg,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: 'center',
  },
  toggleBtnActive: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  toggleBtnPressed: {
    opacity: 0.7,
  },
  toggleBtnText: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightMedium,
  },
  toggleBtnTextActive: {
    color: '#1A0F08',
    fontWeight: FONT.weightBold,
  },

  divider: {
    height: 1,
    backgroundColor: COLORS.border,
    marginVertical: SPACING.md,
  },

  weightSectionTitle: {
    fontSize: FONT.sizeSm,
    color: COLORS.textPrimary,
    fontWeight: FONT.weightBold,
    marginBottom: SPACING.md,
  },

  note: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
    marginTop: SPACING.lg,
    textAlign: 'center',
  },

  bottomBarRow: {
    flexDirection: 'row',
  },
});
