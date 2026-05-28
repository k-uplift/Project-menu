/**
 * WeightSlider — 0~100% 가중치 슬라이더 (개선판)
 *
 * 외부 라이브러리 없이 PanResponder + measure로 구현
 *
 * 변경 포인트:
 *  - pageX (화면 절대 좌표) 기준으로 계산 → 드래그 중에도 정확
 *  - measureInWindow로 트랙의 화면상 위치를 정확히 측정
 *  - 탭만 해도 그 위치로 점프
 *  - PanResponder 콜백을 ref에 저장해서 최신 props 항상 참조
 */

import React, { useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  PanResponder,
} from 'react-native';
import { COLORS, SPACING, FONT } from '../constants/theme';

const TRACK_HEIGHT = 6;
const HANDLE_SIZE = 22;

export default function WeightSlider({ label, value, onChange, min = 0, max = 100 }) {
  const trackRef = useRef(null);
  // 트랙의 화면상 위치/크기 — measureInWindow로 채워짐
  const trackLayout = useRef({ x: 0, width: 0 });

  // 최신 onChange/min/max를 PanResponder가 항상 참조하도록 ref에 저장
  const onChangeRef = useRef(onChange);
  const rangeRef = useRef({ min, max });

  useEffect(() => {
    onChangeRef.current = onChange;
    rangeRef.current = { min, max };
  }, [onChange, min, max]);

  // 트랙 레이아웃 측정
  // (화면이 회전되거나 리렌더 시에도 갱신되도록 onLayout 사용)
  const measureTrack = () => {
    if (trackRef.current) {
      trackRef.current.measureInWindow((x, y, width) => {
        trackLayout.current = { x, width };
      });
    }
  };

  // pageX (화면 절대 X) → value 변환
  const pageXToValue = (pageX) => {
    const { x: trackX, width } = trackLayout.current;
    if (width === 0) return value;

    let ratio = (pageX - trackX) / width;
    ratio = Math.max(0, Math.min(1, ratio));
    const { min: lo, max: hi } = rangeRef.current;
    return Math.round(lo + ratio * (hi - lo));
  };

  // PanResponder는 한 번만 생성 (PanResponder 내부에서 ref만 참조)
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onStartShouldSetPanResponderCapture: () => true,
      onMoveShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponderCapture: () => true,

      // 드래그 시작 시점에 트랙 위치 다시 측정 (혹시 스크롤된 경우 대비)
      onPanResponderGrant: (evt) => {
        if (trackRef.current) {
          trackRef.current.measureInWindow((x, y, width) => {
            trackLayout.current = { x, width };
            // 측정 직후, 시작 위치도 즉시 반영
            const newValue = pageXToValue(evt.nativeEvent.pageX);
            onChangeRef.current && onChangeRef.current(newValue);
          });
        }
      },

      onPanResponderMove: (evt) => {
        const newValue = pageXToValue(evt.nativeEvent.pageX);
        onChangeRef.current && onChangeRef.current(newValue);
      },

      onPanResponderTerminationRequest: () => false,
    })
  ).current;

  const ratio = (value - min) / (max - min);
  const ratioPct = `${Math.max(0, Math.min(1, ratio)) * 100}%`;

  return (
    <View style={styles.wrapper}>
      <View style={styles.headerRow}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.value}>{value}%</Text>
      </View>

      {/* 터치 영역을 충분히 크게 */}
      <View
        ref={trackRef}
        onLayout={measureTrack}
        style={styles.touchArea}
        {...panResponder.panHandlers}
      >
        {/* 트랙 (회색) */}
        <View style={styles.track} />

        {/* 채움 (주황) */}
        <View
          style={[
            styles.fill,
            { width: ratioPct },
          ]}
        />

        {/* 핸들 */}
        <View
          style={[
            styles.handle,
            { left: ratioPct },
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

  // 터치 영역 — 트랙 위아래로 여유를 주어 손가락으로 잡기 쉽게
  touchArea: {
    height: 32,
    justifyContent: 'center',
    paddingVertical: 13, // (32 - TRACK_HEIGHT) / 2 정도
    position: 'relative',
  },
  track: {
    height: TRACK_HEIGHT,
    backgroundColor: COLORS.border,
    borderRadius: TRACK_HEIGHT / 2,
  },
  fill: {
    position: 'absolute',
    left: 0,
    top: 13,
    height: TRACK_HEIGHT,
    backgroundColor: COLORS.primary,
    borderRadius: TRACK_HEIGHT / 2,
  },
  handle: {
    position: 'absolute',
    top: 16 - HANDLE_SIZE / 2, // 트랙 중앙 정렬
    width: HANDLE_SIZE,
    height: HANDLE_SIZE,
    borderRadius: HANDLE_SIZE / 2,
    backgroundColor: COLORS.primary,
    borderWidth: 2,
    borderColor: '#1A0F08',
    marginLeft: -HANDLE_SIZE / 2,
    shadowColor: COLORS.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 4,
    elevation: 4,
  },
});
