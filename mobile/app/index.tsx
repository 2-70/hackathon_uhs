import Ionicons from '@expo/vector-icons/Ionicons';
import { useEffect, useRef } from 'react';
import { useRouter, type Href } from 'expo-router';
import { Animated, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLaundry } from '../src/store';
import { Notice, palette, SpringPressable, styles, type IconName, useReducedMotion } from '../src/ui';

type Shortcut = {
  title: string;
  icon: IconName;
  color: string;
  href: Href;
  washer?: boolean;
};

const shortcuts: Shortcut[] = [
  { title: '옷 추가', icon: 'add', color: palette.peach, href: '/garment' },
  { title: '옷장', icon: 'shirt-outline', color: palette.lilac, href: '/wardrobe' },
  { title: '세탁기', icon: 'options-outline', color: palette.aqua, href: '/machines', washer: true },
  { title: '세탁 계획', icon: 'list-outline', color: palette.blue, href: '/drum' },
];

export default function Home() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { ready, loadError, basketIds, machine, analysisStarted } = useLaundry();
  const hasData = ready && !loadError;
  const count = basketIds.length;
  const canAnalyze = count > 0 && !!machine;
  const planHref: Href = canAnalyze && analysisStarted
    ? { pathname: '/drum', params: { focus: 'plan' } }
    : '/drum';
  const next: { href: Href; label: string } = count === 0
    ? { href: '/wardrobe', label: '옷 고르기' }
    : machine
      ? { href: planHref, label: analysisStarted ? '계획 보기' : '계획 만들기' }
      : { href: '/machines', label: '세탁기 등록' };
  const nextLabel = !ready
    ? '불러오는 중'
    : loadError
      ? '상태 확인 필요'
      : next.label;

  return (
    <ScrollView
      style={home.screen}
      contentContainerStyle={[home.content, { paddingBottom: 102 + insets.bottom }]}
      showsVerticalScrollIndicator={false}
    >
      {loadError && <Notice tone="error">{loadError}</Notice>}

      <SpringPressable
        accessibilityRole="button"
        accessibilityLabel={`드럼에 담은 빨래 ${hasData ? `${count}벌` : '불러오는 중'}. 다음 행동: ${nextLabel}`}
        accessibilityState={{ disabled: !ready || !!loadError }}
        disabled={!ready || !!loadError}
        onPress={() => router.push(next.href)}
        style={({ pressed }) => [home.hero, (pressed || !ready || !!loadError) && styles.dimmed]}
      >
        <View pointerEvents="none" style={home.heroHalo} />
        <View pointerEvents="none" style={home.heroWaveBack} />
        <View pointerEvents="none" style={home.heroWaveFront} />
        <View style={home.heroTop}>
          <View style={home.heroCopy}>
            <Text style={home.eyebrow}>드럼에 담은 빨래</Text>
            <View style={home.countRow}>
              <Text style={home.count}>{hasData ? count : '–'}</Text>
              <Text style={home.countUnit}>벌</Text>
            </View>
          </View>
          <WashingMachine />
        </View>

        <View style={home.heroAction}>
          <Text style={home.heroActionText}>{nextLabel}</Text>
          <Ionicons name="arrow-forward" size={18} color={palette.surface} />
        </View>
      </SpringPressable>

      <View style={home.shortcuts}>
        {shortcuts.map((shortcut) => (
          <SpringPressable
            key={shortcut.title}
            accessibilityRole="button"
            accessibilityLabel={`${shortcut.title} 화면 열기`}
            onPress={() => router.push(shortcut.href)}
            style={({ pressed }) => [home.shortcut, { backgroundColor: shortcut.color }, pressed && styles.dimmed]}
          >
            <View pointerEvents="none" style={home.shortcutOrb} />
            <View style={home.shortcutGlyph} importantForAccessibility="no-hide-descendants">
              {shortcut.washer ? <TinyWasher /> : <Ionicons name={shortcut.icon} size={28} color={palette.ink} />}
            </View>
            <Text style={home.shortcutTitle}>{shortcut.title}</Text>
          </SpringPressable>
        ))}
      </View>
    </ScrollView>
  );
}

function WashingMachine() {
  const reduceMotion = useReducedMotion();
  const bounce = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(1)).current;
  const hasPlayed = useRef(false);

  useEffect(() => {
    if (reduceMotion === true) {
      bounce.setValue(0);
      scale.setValue(1);
      return;
    }
    if (reduceMotion !== false || hasPlayed.current) return;

    hasPlayed.current = true;
    const useNativeDriver = Platform.OS !== 'web';
    bounce.setValue(7);
    scale.setValue(0.97);
    const settle = Animated.parallel([
      Animated.sequence([
        Animated.spring(bounce, { toValue: -2, useNativeDriver, speed: 20, bounciness: 8 }),
        Animated.spring(bounce, { toValue: 0, useNativeDriver, speed: 18, bounciness: 4 }),
      ]),
      Animated.sequence([
        Animated.spring(scale, { toValue: 1.015, useNativeDriver, speed: 20, bounciness: 7 }),
        Animated.spring(scale, { toValue: 1, useNativeDriver, speed: 18, bounciness: 4 }),
      ]),
    ]);
    settle.start();
    return () => {
      settle.stop();
      bounce.stopAnimation();
      scale.stopAnimation();
    };
  }, [bounce, reduceMotion, scale]);

  return (
    <Animated.View
      style={[home.machineWrap, { transform: [{ translateY: bounce }, { scale }] }]}
      importantForAccessibility="no-hide-descendants"
    >
      <View style={home.machineGlow} />
      <View style={home.machineBody}>
        <View style={home.machinePanel}>
          <View style={home.machineDial}>
            <View style={home.machineDialDot} />
            <View style={home.machineDialTick} />
          </View>
          <View style={home.machineDisplay}>
            <View style={home.displayBar} />
            <View style={home.displayLed} />
          </View>
          <View style={home.machineButton} />
        </View>
        <View style={home.machineDoorOuter}>
          <View style={home.machineDoorInner}>
            <View style={home.machineWaterBack} />
            <View style={home.machineWaterFront} />
            <View style={home.machineFace}>
              <View style={home.machineEye}>
                <View style={home.machinePupil} />
                <View style={home.machineEyeShine} />
              </View>
              <View style={home.machineEye}>
                <View style={home.machinePupil} />
                <View style={home.machineEyeShine} />
              </View>
            </View>
            <View style={[home.machineCheek, home.machineCheekLeft]} />
            <View style={[home.machineCheek, home.machineCheekRight]} />
            <View style={home.machineSmile} />
            <View style={home.machineBubbleOne} />
            <View style={home.machineBubbleTwo} />
            <View style={home.machineBubbleThree} />
          </View>
        </View>
        <View style={home.machineLowerSeam} />
        <View style={home.machineFootLeft} />
        <View style={home.machineFootRight} />
      </View>
      <View style={home.machineSparkle}><Ionicons name="sparkles" size={15} color="#FFFDFE" /></View>
    </Animated.View>
  );
}

function TinyWasher() {
  return (
    <View style={home.tinyWasher}>
      <View style={home.tinyPanel}>
        <View style={home.tinyDial} />
        <View style={home.tinyDisplay} />
      </View>
      <View style={home.tinyDoor} />
    </View>
  );
}

const home = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.paper },
  content: {
    flexGrow: 1, width: '100%', maxWidth: 640, alignSelf: 'center',
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 24, gap: 16,
  },
  hero: {
    position: 'relative', overflow: 'hidden', gap: 13, padding: 16, borderRadius: 29,
    borderWidth: 1, borderColor: '#E4DDFF', backgroundColor: '#D9D0FF',
    shadowColor: '#7566BD', shadowOpacity: 0.15, shadowRadius: 18, shadowOffset: { width: 0, height: 8 }, elevation: 4,
  },
  heroHalo: {
    position: 'absolute', width: 220, height: 176, right: -83, top: -91, borderRadius: 100,
    backgroundColor: 'rgba(255,255,255,0.32)', transform: [{ rotate: '-18deg' }],
  },
  heroWaveBack: {
    position: 'absolute', width: 290, height: 102, left: 62, bottom: -67, borderRadius: 80,
    backgroundColor: 'rgba(246,243,255,0.43)', transform: [{ rotate: '-10deg' }],
  },
  heroWaveFront: {
    position: 'absolute', width: 238, height: 74, left: -91, bottom: -54, borderRadius: 80,
    backgroundColor: 'rgba(189,177,255,0.28)', transform: [{ rotate: '13deg' }],
  },
  heroTop: { minHeight: 154, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  heroCopy: { flex: 1, minWidth: 0, alignSelf: 'stretch', justifyContent: 'center', gap: 2 },
  eyebrow: { color: '#4F4777', fontSize: 12, lineHeight: 16, fontWeight: '800', marginBottom: 5 },
  countRow: { flexDirection: 'row', alignItems: 'baseline', gap: 5 },
  count: { color: '#28243E', fontSize: 52, lineHeight: 59, letterSpacing: -2, fontWeight: '900', fontVariant: ['tabular-nums'] },
  countUnit: { color: '#4F4777', fontSize: 14, lineHeight: 19, fontWeight: '800' },
  heroAction: {
    minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    paddingHorizontal: 14, borderRadius: 16, backgroundColor: '#6E5AE8',
    shadowColor: '#6553CF', shadowOpacity: 0.17, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 2,
  },
  heroActionText: { flexShrink: 1, color: palette.surface, fontSize: 14, lineHeight: 19, fontWeight: '800', textAlign: 'center' },
  machineWrap: { width: 132, height: 154, flexShrink: 0, justifyContent: 'center', alignItems: 'center' },
  machineGlow: {
    position: 'absolute', width: 127, height: 120, left: 1, top: 20, borderRadius: 28,
    backgroundColor: 'rgba(157,139,239,0.28)', transform: [{ rotate: '8deg' }],
  },
  machineBody: {
    width: 116, height: 132, alignItems: 'center', borderWidth: 1.5, borderColor: '#F8F5FF',
    borderRadius: 23, backgroundColor: '#FFFEFF', paddingHorizontal: 8, paddingTop: 9,
    shadowColor: '#6654BC', shadowOpacity: 0.16, shadowRadius: 10, shadowOffset: { width: 0, height: 5 }, elevation: 3,
  },
  machinePanel: { width: '100%', height: 25, flexDirection: 'row', alignItems: 'center', gap: 6, borderBottomWidth: 1, borderColor: '#EEE9FA', paddingBottom: 6 },
  machineDial: { width: 21, height: 21, justifyContent: 'center', alignItems: 'center', borderRadius: 11, borderWidth: 2, borderColor: '#C3B8F7', backgroundColor: '#F5F2FF' },
  machineDialDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: '#8171E7' },
  machineDialTick: { position: 'absolute', width: 2, height: 4, top: 1, borderRadius: 1, backgroundColor: '#6555C8' },
  machineDisplay: { flex: 1, height: 17, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 5, borderRadius: 6, backgroundColor: '#E8F8F3' },
  displayBar: { width: '48%', height: 3, borderRadius: 2, backgroundColor: '#7EBAAB' },
  displayLed: { width: 4, height: 4, borderRadius: 2, backgroundColor: '#6CC3AA' },
  machineButton: { width: 9, height: 9, borderRadius: 5, backgroundColor: '#FFD1BF' },
  machineDoorOuter: {
    width: 82, height: 82, marginTop: 8, justifyContent: 'center', alignItems: 'center',
    borderRadius: 42, borderWidth: 5, borderColor: '#D7D0F5', backgroundColor: '#F0EDFC',
    shadowColor: '#7868C5', shadowOpacity: 0.13, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 1,
  },
  machineDoorInner: {
    width: 70, height: 70, justifyContent: 'center', alignItems: 'center', overflow: 'hidden',
    borderRadius: 36, borderWidth: 1.5, borderColor: '#B6A9F0', backgroundColor: '#D5CEFF',
  },
  machineWaterBack: { position: 'absolute', width: 92, height: 46, left: -13, top: 36, borderRadius: 30, backgroundColor: 'rgba(119,101,229,0.48)', transform: [{ rotate: '-13deg' }] },
  machineWaterFront: { position: 'absolute', width: 91, height: 38, right: -15, top: 42, borderRadius: 28, backgroundColor: 'rgba(103,84,222,0.72)', transform: [{ rotate: '12deg' }] },
  machineFace: { position: 'absolute', top: 18, flexDirection: 'row', gap: 13, alignItems: 'center' },
  machineEye: { width: 14, height: 16, borderRadius: 8, backgroundColor: '#FFFDFE', alignItems: 'center', justifyContent: 'center', shadowColor: '#5C4CA8', shadowOpacity: 0.12, shadowRadius: 2, elevation: 1 },
  machinePupil: { width: 7, height: 9, borderRadius: 5, backgroundColor: '#312958', marginTop: 2 },
  machineEyeShine: { position: 'absolute', width: 3.5, height: 3.5, left: 3, top: 3, borderRadius: 2, backgroundColor: '#FFFFFF' },
  machineCheek: { position: 'absolute', top: 39, width: 9, height: 5, borderRadius: 6, backgroundColor: 'rgba(255,171,194,0.88)' },
  machineCheekLeft: { left: 13 },
  machineCheekRight: { right: 13 },
  machineSmile: { position: 'absolute', top: 38, width: 15, height: 9, borderBottomWidth: 2, borderBottomColor: '#43386D', borderRadius: 12 },
  machineBubbleOne: { position: 'absolute', width: 7, height: 7, right: 9, top: 10, borderRadius: 4, borderWidth: 1, borderColor: 'rgba(255,255,255,0.8)', backgroundColor: 'rgba(255,255,255,0.4)' },
  machineBubbleTwo: { position: 'absolute', width: 5, height: 5, right: 16, top: 5, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.9)' },
  machineBubbleThree: { position: 'absolute', width: 4, height: 4, left: 10, top: 53, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.84)' },
  machineLowerSeam: { position: 'absolute', width: 60, height: 1, left: 28, bottom: 5, backgroundColor: '#F0ECF8' },
  machineFootLeft: { position: 'absolute', left: 20, bottom: -3, width: 14, height: 6, borderRadius: 3, backgroundColor: '#B9AFE8' },
  machineFootRight: { position: 'absolute', right: 20, bottom: -3, width: 14, height: 6, borderRadius: 3, backgroundColor: '#B9AFE8' },
  machineSparkle: { position: 'absolute', top: 6, right: 5, width: 25, height: 25, alignItems: 'center', justifyContent: 'center', borderRadius: 13, backgroundColor: 'rgba(139,121,233,0.78)' },
  tinyWasher: { width: 30, height: 36, borderWidth: 1.5, borderColor: '#B9AFE8', borderRadius: 8, backgroundColor: '#FFFDFE', paddingHorizontal: 3, paddingTop: 3, alignItems: 'center' },
  tinyPanel: { width: '100%', height: 6, flexDirection: 'row', alignItems: 'center', gap: 2, borderBottomWidth: 1, borderColor: '#EEE9FA', paddingBottom: 2 },
  tinyDial: { width: 4, height: 4, borderRadius: 2, backgroundColor: '#8272E2' },
  tinyDisplay: { flex: 1, height: 3, borderRadius: 1, backgroundColor: '#BCEBDD' },
  tinyDoor: { width: 18, height: 18, marginTop: 3, borderRadius: 10, borderWidth: 1.5, borderColor: '#C7BDF2', backgroundColor: '#E3DDFF' },
  shortcuts: { flexGrow: 1, minHeight: 320, maxHeight: 420, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignContent: 'stretch', rowGap: 12 },
  shortcutOrb: { position: 'absolute', width: 78, height: 78, top: -32, right: -19, borderRadius: 40, backgroundColor: 'rgba(255,255,255,0.3)' },
  shortcut: {
    position: 'relative', overflow: 'hidden', width: '48.5%', minHeight: 154, maxHeight: 205, flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    gap: 10, paddingHorizontal: 12, paddingVertical: 15, borderWidth: 1, borderColor: 'rgba(255,255,255,0.78)', borderRadius: 24,
    shadowColor: '#8172B7', shadowOpacity: 0.1, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 2,
  },
  shortcutGlyph: {
    width: 60, height: 60, alignItems: 'center', justifyContent: 'center',
    borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.62)',
  },
  shortcutTitle: { color: '#332F43', fontSize: 15, lineHeight: 20, fontWeight: '800', textAlign: 'center' },
});
