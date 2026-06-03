/**
 * KeywordScreen — 키워드 확인 (STEP 02)
 *
 * LLM 이 뽑은 시드 14 안의 태그를 확인·제거. 추천 키워드도 시드 14 안에서만.
 * 시드 외 단어는 백엔드 enum 잠금이라 추천에 반영 안 되니, 사용자가 *시드 안*
 * 에서만 고르도록 입력 자유텍스트는 제거.
 */

import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
} from 'react-native';

import ScreenContainer from '../components/ScreenContainer';
import PrimaryButton from '../components/PrimaryButton';
import KeywordTag from '../components/KeywordTag';
import { createUserKeyword } from '../services/keywordService';
import { SUGGESTED_KEYWORDS } from '../constants/config';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function KeywordScreen({ route, navigation }) {
  const { analyzeResult } = route.params;

  // 키워드 상태
  const [keywords, setKeywords] = useState(
    (analyzeResult.keywords || []).map((k) => ({ ...k, selected: true }))
  );

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
    if (keywords.some((k) => k.label === trimmed)) {
      Alert.alert('이미 추가됨', '같은 키워드가 이미 있어요.');
      return;
    }
    const newKw = createUserKeyword(trimmed);
    setKeywords((prev) => [...prev, { ...newKw, selected: true }]);
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
      context: {},
    });
  };

  // 추천 키워드 — 시드 14 안에서 미사용된 것 중 *랜덤 8개* 회전.
  // useMemo 로 키워드 상태 변할 때마다 다시 섞기 (사용자가 추가하면 다음 풀 달라짐).
  const suggestions = useMemo(() => {
    const usedLabels = new Set(keywords.map((k) => k.label));
    const pool = SUGGESTED_KEYWORDS.filter((s) => !usedLabels.has(s));
    // 셔플 (Fisher-Yates) → 상위 8개
    const shuffled = [...pool];
    for (let i = shuffled.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled.slice(0, 8);
  }, [keywords]);

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

      {/* 추천 키워드 — 시드 14 안에서 8개 랜덤 회전 */}
      {suggestions.length > 0 && (
        <>
          <Text style={[styles.sectionLabel, { marginTop: SPACING.lg }]}>
            이런 키워드는 어떠세요?
          </Text>
          <View style={styles.tagWrap}>
            {suggestions.map((s) => (
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

      <Text style={styles.note}>
        💡 선택된 키워드만 추천에 반영돼요
      </Text>
    </ScreenContainer>
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
