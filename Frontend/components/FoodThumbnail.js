/**
 * FoodThumbnail — 음식 썸네일 컴포넌트
 *
 * 이모지를 대체하는 깔끔한 시각 표현
 *
 * 디자인:
 *  - 음식 카테고리별 그라데이션 배경
 *  - 음식 이름 첫 글자 (이니셜) 표시
 *  - 추후 실제 이미지로 교체 시: imageUrl prop 받으면 그걸 우선 표시
 *
 * 사용:
 *   <FoodThumbnail food={foodItem} size="md" />
 *   <FoodThumbnail food={foodItem} size="lg" imageUrl="..." />
 */

import React from 'react';
import { View, Text, Image, StyleSheet } from 'react-native';
import { COLORS, RADIUS, FONT } from '../constants/theme';

// 음식 태그 → 색상 매핑
// (실제 음식 이미지가 없을 때 카테고리 색상으로 시각적 구분)
const TAG_COLORS = {
  국물있는: ['#FF7A33', '#C75A1F'],
  따뜻한: ['#FF9F47', '#E66B1F'],
  얼큰한: ['#FF5252', '#C62828'],
  매운: ['#FF5252', '#C62828'],
  담백한: ['#A8B5A0', '#6B7A60'],
  진한: ['#8B5A2B', '#5C3A1C'],
  가벼운: ['#7DB87A', '#4A8A47'],
  든든한: ['#B7791F', '#7C5012'],
  쫄깃한: ['#D4A574', '#A07444'],
  바삭한: ['#E8A95B', '#B57430'],
  시원한: ['#5BA3D4', '#2E6B95'],
};

// 기본 색상 풀 (태그 매칭 안 될 때)
const DEFAULT_COLORS = [
  ['#FF7A33', '#C75A1F'],
  ['#8B5A2B', '#5C3A1C'],
  ['#A8B5A0', '#6B7A60'],
  ['#7DB87A', '#4A8A47'],
];

/** 음식 ID로부터 안정적인 색상 선택 */
function pickColors(food) {
  // 태그에 우선 매칭되는 색상이 있으면 사용
  for (const tag of food.tags || []) {
    if (TAG_COLORS[tag]) return TAG_COLORS[tag];
  }
  // 없으면 음식 ID 해시로 결정적 선택
  const hash = (food.id || '').split('').reduce(
    (sum, c) => sum + c.charCodeAt(0),
    0
  );
  return DEFAULT_COLORS[hash % DEFAULT_COLORS.length];
}

/**
 * 음식 이름의 표시용 이니셜
 * 한글이면 첫 글자, 영어면 첫 두 글자
 */
function getInitial(name) {
  if (!name) return '';
  const first = name.charAt(0);
  // 한글 범위 체크
  if (/[\uac00-\ud7af]/.test(first)) {
    return first;
  }
  return name.slice(0, 2).toUpperCase();
}

const SIZE_PRESETS = {
  sm: { wrapper: 36, font: 14, radius: RADIUS.sm },
  md: { wrapper: 56, font: 22, radius: RADIUS.md },
  lg: { wrapper: 72, font: 28, radius: RADIUS.lg },
};

export default function FoodThumbnail({
  food,
  size = 'md',
  imageUrl, // 추후 실제 이미지 URL이 들어오면 자동으로 이미지 표시
}) {
  const preset = SIZE_PRESETS[size] || SIZE_PRESETS.md;
  const [colorMain, colorDark] = pickColors(food);
  const initial = getInitial(food.name);

  // 실제 이미지 URL이 있으면 이미지 우선 표시
  if (imageUrl) {
    return (
      <View
        style={[
          styles.wrapper,
          {
            width: preset.wrapper,
            height: preset.wrapper,
            borderRadius: preset.radius,
          },
        ]}
      >
        <Image
          source={{ uri: imageUrl }}
          style={[
            styles.image,
            { borderRadius: preset.radius },
          ]}
          resizeMode="cover"
        />
      </View>
    );
  }

  // 더미: 그라데이션 흉내 (메인 색상 + 우상단에 어두운 색상 도트)
  return (
    <View
      style={[
        styles.wrapper,
        {
          width: preset.wrapper,
          height: preset.wrapper,
          borderRadius: preset.radius,
          backgroundColor: colorMain,
        },
      ]}
    >
      {/* 우상단 어두운 도트 — 입체감 표현 */}
      <View
        style={[
          styles.darkDot,
          {
            backgroundColor: colorDark,
            borderTopRightRadius: preset.radius,
          },
        ]}
      />

      {/* 이니셜 */}
      <Text
        style={[
          styles.initial,
          {
            fontSize: preset.font,
          },
        ]}
      >
        {initial}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  darkDot: {
    position: 'absolute',
    top: 0,
    right: 0,
    width: '50%',
    height: '50%',
    opacity: 0.5,
  },
  initial: {
    color: '#FFF7F0',
    fontWeight: FONT.weightExtra,
    letterSpacing: -0.5,
  },
});
