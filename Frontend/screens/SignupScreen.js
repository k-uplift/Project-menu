/**
 * SignupScreen — 회원가입 화면
 *
 * - 이메일 / 비밀번호 / 비밀번호 확인 입력
 * - 클라이언트 검증(형식·길이·일치) 후 백엔드 /auth/signup 호출
 * - 성공 시 자동 로그인(토큰 저장) → Home 으로 이동(스택 리셋)
 *
 * 비밀번호 최소 길이는 백엔드(MIN_PASSWORD_LEN=8)와 맞춘다.
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
import { signup } from '../services/authService';
import { COLORS, SPACING, RADIUS, FONT } from '../constants/theme';

const MIN_PASSWORD_LEN = 8;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function SignupScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSignup = async () => {
    const mail = email.trim();
    if (!EMAIL_RE.test(mail)) {
      Alert.alert('이메일 확인', '올바른 이메일 형식을 입력해주세요. (예: you@example.com)');
      return;
    }
    if (password.length < MIN_PASSWORD_LEN) {
      Alert.alert('비밀번호 확인', `비밀번호는 최소 ${MIN_PASSWORD_LEN}자 이상이어야 합니다.`);
      return;
    }
    if (password !== confirm) {
      Alert.alert('비밀번호 확인', '비밀번호가 서로 일치하지 않습니다.');
      return;
    }

    setLoading(true);
    try {
      await signup(mail, password);
      // 가입 + 자동 로그인 완료 → 홈으로 (뒤로가기로 가입화면 복귀 방지)
      navigation.reset({ index: 0, routes: [{ name: 'Home' }] });
    } catch (e) {
      Alert.alert('회원가입 실패', e.message || '잠시 후 다시 시도해주세요.');
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
          {/* 상단 바 */}
          <Pressable
            onPress={() => navigation.goBack()}
            hitSlop={12}
            style={styles.backBtn}
          >
            <Text style={styles.backText}>‹ 로그인으로</Text>
          </Pressable>

          <Text style={styles.title}>회원가입</Text>
          <Text style={styles.sub}>이메일과 비밀번호로 계정을 만들어요.</Text>

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
            <Text style={styles.label}>비밀번호 (최소 {MIN_PASSWORD_LEN}자)</Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="비밀번호"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              secureTextEntry
              autoCapitalize="none"
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>비밀번호 확인</Text>
            <TextInput
              value={confirm}
              onChangeText={setConfirm}
              placeholder="비밀번호 다시 입력"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              secureTextEntry
              autoCapitalize="none"
              onSubmitEditing={handleSignup}
              returnKeyType="go"
            />
          </View>

          <View style={{ marginTop: SPACING.lg }}>
            <PrimaryButton label="회원가입" onPress={handleSignup} loading={loading} />
          </View>

          <View style={styles.loginRow}>
            <Text style={styles.loginHint}>이미 계정이 있으신가요?</Text>
            <Pressable onPress={() => navigation.goBack()} hitSlop={8}>
              <Text style={styles.loginLink}>로그인</Text>
            </Pressable>
          </View>
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
  backBtn: {
    position: 'absolute',
    top: SPACING.md,
    left: 0,
  },
  backText: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightMedium,
  },
  title: {
    fontSize: FONT.sizeXl,
    fontWeight: FONT.weightExtra,
    color: COLORS.textPrimary,
    marginBottom: SPACING.xs,
  },
  sub: {
    fontSize: FONT.sizeSm,
    color: COLORS.textSecondary,
    marginBottom: SPACING.xl,
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
  loginRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: SPACING.xl,
    gap: SPACING.sm,
  },
  loginHint: {
    color: COLORS.textSecondary,
    fontSize: FONT.sizeSm,
  },
  loginLink: {
    color: COLORS.primary,
    fontSize: FONT.sizeSm,
    fontWeight: FONT.weightBold,
  },
});
