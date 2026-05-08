/**
 * App.js — 앱 진입점
 *
 * 네비게이션 구성:
 *   Home → Keyword → Recommend → Restaurant → RestaurantDetail
 *   Home → MyPage (모달 스타일)
 */

import 'react-native-gesture-handler';
import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import HomeScreen from './screens/HomeScreen';
import KeywordScreen from './screens/KeywordScreen';
import RecommendScreen from './screens/RecommendScreen';
import RestaurantScreen from './screens/RestaurantScreen';
import RestaurantDetailScreen from './screens/RestaurantDetailScreen';
import MyPageScreen from './screens/MyPageScreen';

import { COLORS } from './constants/theme';

const Stack = createNativeStackNavigator();

const navTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    background: COLORS.bg,
    card: COLORS.bg,
    text: COLORS.textPrimary,
    border: COLORS.border,
    primary: COLORS.primary,
  },
};

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <NavigationContainer theme={navTheme}>
        <Stack.Navigator
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: COLORS.bg },
            animation: 'slide_from_right',
          }}
        >
          <Stack.Screen name="Home" component={HomeScreen} />
          <Stack.Screen name="Keyword" component={KeywordScreen} />
          <Stack.Screen name="Recommend" component={RecommendScreen} />
          <Stack.Screen name="Restaurant" component={RestaurantScreen} />
          <Stack.Screen
            name="RestaurantDetail"
            component={RestaurantDetailScreen}
          />
          <Stack.Screen
            name="MyPage"
            component={MyPageScreen}
            options={{ animation: 'slide_from_bottom' }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
