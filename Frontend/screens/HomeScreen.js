/**
 * HomeScreen — 자연어 입력 화면 (STEP 01)
 *
 * - 자유 텍스트 입력
 * - 예시 문장 탭하면 자동 채움
 * - 빈 입력 예외 처리
 * - "분석" 버튼 → 키워드 분석 후 KeywordScreen 으로 이동
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  Pressable,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';

import ScreenContainer from '../components/ScreenContainer';
import PrimaryButton from '../components/PrimaryButton';
import LoadingOverlay from '../components/LoadingOverlay';
import { analyzeKeywords } from '../services/keywordService';
import { EXAMPLE_PROMPTS } from '../constants/config';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function HomeScreen({ navigation }) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);

  const handleExample = (example) => {
    setText(example);
  };

  const handleAnalyze = async () => {
    const trimmed = text.trim();

    // 빈 입력 예외 처리
    if (trimmed.length === 0) {
      Alert.alert('입력해주세요', '오늘의 기분이나 먹고 싶은 느낌을 자유롭게 적어보세요.');
      return;
    }
    if (trimmed.length < 2) {
      Alert.alert('조금 더 적어주세요', '최소 2글자 이상 입력해주세요.');
      return;
    }

    setLoading(true);
    try {
      const result = await analyzeKeywords(trimmed);
      navigation.navigate('Keyword', { analyzeResult: result });
    } catch (e) {
      Alert.alert('분석 실패', '잠시 후 다시 시도해주세요.');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // 로딩 중에는 LoadingOverlay 풀스크린 표시
  if (loading) {
    return (
      <ScreenContainer step="home" scroll={false}>
        <LoadingOverlay originalText={text} />
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer step="home" scroll>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* 헤드라인 */}
        <Text style={styles.headline}>
          오늘의 한 끼,{'\n'}
          <Text style={styles.headlineAccent}>기분으로</Text> 말해보세요.
        </Text>
        <Text style={styles.sub}>
          자연어로 입력하면 AI가 의미를 분석해{'\n'}맞춤 메뉴와 주변 음식점을 찾아드려요.
        </Text>

        {/* 입력창 */}
        <View style={styles.inputCard}>
          <TextInput
            value={text}
            onChangeText={setText}
            placeholder="비 오는 날 혼자 먹을 따뜻하고 국물 있는 것..."
            placeholderTextColor={COLORS.textMuted}
            style={styles.input}
            multiline
            maxLength={200}
            textAlignVertical="top"
          />
          <Text style={styles.counter}>{text.length} / 200</Text>
        </View>

        {/* 예시 문장 */}
        <Text style={styles.exampleLabel}>예를 들면</Text>
        <View style={styles.exampleList}>
          {EXAMPLE_PROMPTS.map((ex) => (
            <Pressable
              key={ex}
              onPress={() => handleExample(ex)}
              style={({ pressed }) => [styles.exampleItem, pressed && styles.examplePressed]}
            >
              <Text style={styles.exampleText}>{ex}</Text>
              <Text style={styles.exampleArrow}>›</Text>
            </Pressable>
          ))}
        </View>

        {/* 분석 버튼 */}
        <View style={{ marginTop: SPACING.xl }}>
          <PrimaryButton label="분석 시작 →" onPress={handleAnalyze} />
        </View>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  headline: {
    fontSize: FONT.sizeXl,
    fontWeight: FONT.weightExtra,
    color: COLORS.textPrimary,
    lineHeight: 32,
    marginBottom: SPACING.md,
  },
  headlineAccent: {
    color: COLORS.primary,
  },
  sub: {
    fontSize: FONT.sizeSm,
    color: COLORS.textSecondary,
    lineHeight: 20,
    marginBottom: SPACING.xl,
  },

  inputCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: SPACING.md,
    marginBottom: SPACING.xl,
  },
  input: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeBase,
    minHeight: 80,
    lineHeight: 22,
  },
  counter: {
    color: COLORS.textMuted,
    fontSize: 11,
    textAlign: 'right',
    marginTop: SPACING.xs,
  },

  exampleLabel: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeXs,
    marginBottom: SPACING.sm,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  exampleList: {
    gap: SPACING.xs,
  },
  exampleItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: SPACING.md,
    paddingHorizontal: SPACING.md,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  examplePressed: {
    opacity: 0.7,
    backgroundColor: COLORS.surfaceAlt,
  },
  exampleText: {
    color: COLORS.textPrimary,
    fontSize: FONT.sizeSm,
  },
  exampleArrow: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeMd,
  },
});
