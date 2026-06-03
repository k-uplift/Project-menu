/**
 * LoginScreen — 로그인 화면
 *
 * - 이메일 / 비밀번호 입력 → 백엔드 /auth/login 호출
 * - 성공 시 토큰 저장(authService) 후 Home 으로 이동(스택 리셋)
 * - "회원가입" → SignupScreen,  "둘러보기" → 로그인 없이 Home
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
import { login } from '../services/authService';
import { APP_INFO } from '../constants/config';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

export default function LoginScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  // 로그인/둘러보기 후에는 뒤로가기로 로그인 화면에 돌아오지 않도록 스택을 리셋
  const goHome = () =>
    navigation.reset({ index: 0, routes: [{ name: 'Home' }] });

  const handleLogin = async () => {
    if (!email.trim() || !password) {
      Alert.alert('입력 확인', '이메일과 비밀번호를 모두 입력해주세요.');
      return;
    }
    setLoading(true);
    try {
      await login(email.trim(), password);
      goHome();
    } catch (e) {
      Alert.alert('로그인 실패', e.message || '잠시 후 다시 시도해주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScreenContainer scroll={false}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.body}>
          {/* 브랜딩 */}
          <View style={styles.brandWrap}>
            <Text style={styles.brand}>{APP_INFO.name}</Text>
            <Text style={styles.tagline}>{APP_INFO.tagline}</Text>
          </View>

          <Text style={styles.title}>로그인</Text>

          {/* 입력 폼 */}
          <View style={styles.field}>
            <Text style={styles.label}>이메일</Text>
            <TextInput
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>비밀번호</Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="비밀번호"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              secureTextEntry
              autoCapitalize="none"
              onSubmitEditing={handleLogin}
              returnKeyType="go"
            />
          </View>

          <View style={{ marginTop: SPACING.lg }}>
            <PrimaryButton label="로그인" onPress={handleLogin} loading={loading} />
          </View>

          {/* 회원가입 이동 */}
          <View style={styles.signupRow}>
            <Text style={styles.signupHint}>아직 계정이 없으신가요?</Text>
            <Pressable onPress={() => navigation.navigate('Signup')} hitSlop={8}>
              <Text style={styles.signupLink}>회원가입</Text>
            </Pressable>
          </View>

          {/* 둘러보기 */}
          <Pressable onPress={goHome} hitSlop={8} style={styles.skipBtn}>
            <Text style={styles.skipText}>로그인 없이 둘러보기 →</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  body: {
    flex: 1,
    justifyContent: 'center',
  },
  brandWrap: {
    alignItems: 'center',
    marginBottom: SPACING.xxl,
  },
  brand: {
    fontSize: FONT.sizeXxl,
    fontWeight: FONT.weightExtra,
    color: COLORS.primary,
    letterSpacing: -1,
  },
  tagline: {
    fontSize: FONT.sizeSm,
    color: COLORS.textSecondary,
    marginTop: SPACING.xs,
  },
  title: {
    fontSize: FONT.sizeLg,
    fontWeight: FONT.weightBold,
    color: COLORS.textPrimary,
    marginBottom: SPACING.lg,
  },
  field: {
    marginBottom: SPACING.md,
  },
  label: {
    fontSize: FONT.sizeXs,
    color: COLORS.textMuted,
    marginBottom: SPACING.xs,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  input: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.md,
    color: COLORS.textPrimary,
    fontSize: FONT.sizeBase,
  },
  signupRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: SPACING.xl,
    gap: SPACING.sm,
  },
  signupHint: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
  },
  signupLink: {
    color: COLORS.primary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
  },
  skipBtn: {
    alignItems: 'center',
    marginTop: SPACING.xl,
  },
  skipText: {
    color: COLORS.textMuted,
    fontSize: FONT.sizeSm,
  },
});
