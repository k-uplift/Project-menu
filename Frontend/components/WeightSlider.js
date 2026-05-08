/**
 * WeightSlider — 0~100% 가중치 슬라이더
 *
 * 외부 라이브러리 없이 React Native 기본 PanResponder로 구현
 * (Expo에서 추가 설치 없이 바로 동작)
 *
 * 첨부 이미지의 디자인 그대로:
 *  - 좌측: 라벨
 *  - 우측: 퍼센트 (주황)
 *  - 슬라이더: 회색 트랙 + 주황 채움 + 주황 핸들
 */

import React, { useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  PanResponder,
  Animated,
} from 'react-native';
import { COLORS, SPACING, FONT } from '../constants/theme';

const TRACK_HEIGHT = 4;
const HANDLE_SIZE = 20;

export default function WeightSlider({ label, value, onChange, min = 0, max = 100 }) {
  const [trackWidth, setTrackWidth] = useState(0);

  // 현재 value를 0~1 비율로
  const ratio = (value - min) / (max - min);

  // PanResponder로 드래그 처리
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {},
      onPanResponderMove: (evt, gestureState) => {
        if (trackWidth === 0) return;
        // 드래그 위치를 트랙 내 비율로 변환
        const touchX = evt.nativeEvent.locationX;
        let newRatio = touchX / trackWidth;
        newRatio = Math.max(0, Math.min(1, newRatio));
        const newValue = Math.round(min + newRatio * (max - min));
        onChange(newValue);
      },
    })
  ).current;

  return (
    <View style={styles.wrapper}>
      <View style={styles.headerRow}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.value}>{value}%</Text>
      </View>

      <View
        style={styles.trackContainer}
        onLayout={(e) => setTrackWidth(e.nativeEvent.layout.width)}
        {...panResponder.panHandlers}
      >
        {/* 회색 트랙 */}
        <View style={styles.track} />

        {/* 주황 채움 */}
        <View
          style={[
            styles.fill,
            { width: `${ratio * 100}%` },
          ]}
        />

        {/* 핸들 */}
        <View
          style={[
            styles.handle,
            {
              left: `${ratio * 100}%`,
              marginLeft: -HANDLE_SIZE / 2,
            },
          ]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginBottom: SPACING.lg,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  label: {
    fontSize: FONT.sizeSm,
    color: COLORS.textSecondary,
  },
  value: {
    fontSize: FONT.sizeSm,
    color: COLORS.primary,
    fontWeight: FONT.weightExtra,
  },

  trackContainer: {
    height: HANDLE_SIZE + 8, // 터치 영역 확장
    justifyContent: 'center',
    paddingVertical: 8,
  },
  track: {
    height: TRACK_HEIGHT,
    backgroundColor: COLORS.border,
    borderRadius: TRACK_HEIGHT / 2,
  },
  fill: {
    position: 'absolute',
    left: 0,
    top: '50%',
    marginTop: -TRACK_HEIGHT / 2,
    height: TRACK_HEIGHT,
    backgroundColor: COLORS.primary,
    borderRadius: TRACK_HEIGHT / 2,
  },
  handle: {
    position: 'absolute',
    top: '50%',
    marginTop: -HANDLE_SIZE / 2,
    width: HANDLE_SIZE,
    height: HANDLE_SIZE,
    borderRadius: HANDLE_SIZE / 2,
    backgroundColor: COLORS.primary,
    borderWidth: 2,
    borderColor: '#1A0F08',
    shadowColor: COLORS.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 4,
    elevation: 3,
  },
});
