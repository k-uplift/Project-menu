/**
 * App.js — 앱 진입점
 *
 * 네비게이션 구성:
 *   Home → Keyword → Recommend → Restaurant → RestaurantDetail
 *   Home → MyPage (모달 스타일)
 */

import 'react-native-gesture-handler';
import React, { useEffect, useState } from 'react';
import { View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import LoginScreen from './screens/LoginScreen';
import SignupScreen from './screens/SignupScreen';
import HomeScreen from './screens/HomeScreen';
import KeywordScreen from './screens/KeywordScreen';
import RecommendScreen from './screens/RecommendScreen';
import RestaurantScreen from './screens/RestaurantScreen';
import RestaurantDetailScreen from './screens/RestaurantDetailScreen';
import MyPageScreen from './screens/MyPageScreen';

import { isLoggedIn } from './services/authService';
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
  // 저장된 토큰이 있으면 로그인 화면을 건너뛰고 바로 Home 으로 시작
  const [initialRoute, setInitialRoute] = useState(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      let logged = false;
      try {
        logged = await isLoggedIn();
      } catch (e) {
        logged = false;
      }
      if (mounted) setInitialRoute(logged ? 'Home' : 'Login');
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // 로그인 상태 확인 전에는 빈 화면(스플래시)을 잠깐 보여준다
  if (initialRoute === null) {
    return <View style={{ flex: 1, backgroundColor: COLORS.bg }} />;
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <NavigationContainer theme={navTheme}>
        <Stack.Navigator
          initialRouteName={initialRoute}
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: COLORS.bg },
            animation: 'slide_from_right',
          }}
        >
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="Signup" component={SignupScreen} />
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
