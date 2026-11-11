import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter, type Href } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLaundry } from '../src/store';
import { Notice, palette, styles, type IconName } from '../src/ui';

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

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`드럼에 담은 빨래 ${hasData ? `${count}벌` : '불러오는 중'}. 다음 행동: ${nextLabel}`}
        accessibilityState={{ disabled: !ready || !!loadError }}
        disabled={!ready || !!loadError}
        onPress={() => router.push(next.href)}
        style={({ pressed }) => [home.hero, (pressed || !ready || !!loadError) && styles.dimmed]}
      >
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
      </Pressable>

      <View style={home.shortcuts}>
        {shortcuts.map((shortcut) => (
          <Pressable
            key={shortcut.title}
            accessibilityRole="button"
            accessibilityLabel={`${shortcut.title} 화면 열기`}
            onPress={() => router.push(shortcut.href)}
            style={({ pressed }) => [home.shortcut, { backgroundColor: shortcut.color }, pressed && styles.dimmed]}
          >
            <View style={home.shortcutGlyph} importantForAccessibility="no-hide-descendants">
              {shortcut.washer ? <TinyWasher /> : <Ionicons name={shortcut.icon} size={28} color={palette.ink} />}
            </View>
            <Text style={home.shortcutTitle}>{shortcut.title}</Text>
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

function WashingMachine() {
  return (
    <View style={home.machineWrap} importantForAccessibility="no-hide-descendants">
      <View style={home.machineShadow} />
      <View style={home.machineBody}>
        <View style={home.machinePanel}>
          <View style={home.machineDial}><View style={home.machineDialDot} /></View>
          <View style={home.machineDisplay}>
            <View style={home.displayLine} />
            <View style={[home.displayLine, home.displayShort]} />
          </View>
          <View style={home.machineButton} />
        </View>
        <View style={home.machineDoorOuter}>
          <View style={home.machineDoorInner}>
            <Ionicons name="shirt-outline" size={34} color={palette.accent} />
            <View style={home.machineBubbleOne} />
            <View style={home.machineBubbleTwo} />
          </View>
        </View>
        <View style={home.machineFootLeft} />
        <View style={home.machineFootRight} />
      </View>
    </View>
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
    overflow: 'hidden', gap: 13, padding: 16, borderRadius: 25,
    borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.coral,
    shadowColor: palette.ink, shadowOpacity: 0.12, shadowRadius: 0, shadowOffset: { width: 0, height: 5 }, elevation: 3,
  },
  heroTop: { minHeight: 148, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  heroCopy: { flex: 1, minWidth: 0, alignSelf: 'stretch', justifyContent: 'center', gap: 2 },
  eyebrow: { color: palette.ink, fontSize: 12, lineHeight: 16, fontWeight: '800', marginBottom: 5 },
  countRow: { flexDirection: 'row', alignItems: 'baseline', gap: 5 },
  count: { color: palette.ink, fontSize: 52, lineHeight: 59, letterSpacing: -2, fontWeight: '900', fontVariant: ['tabular-nums'] },
  countUnit: { color: palette.ink, fontSize: 14, lineHeight: 19, fontWeight: '800' },
  heroAction: {
    minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    paddingHorizontal: 14, borderRadius: 14, backgroundColor: palette.accent,
  },
  heroActionText: { flexShrink: 1, color: palette.surface, fontSize: 14, lineHeight: 19, fontWeight: '800', textAlign: 'center' },
  machineWrap: { width: 124, height: 148, flexShrink: 0, justifyContent: 'center', alignItems: 'center' },
  machineShadow: {
    position: 'absolute', width: 112, height: 130, left: 9, top: 13,
    borderWidth: 2, borderColor: palette.ink, borderRadius: 17, backgroundColor: palette.peach,
  },
  machineBody: {
    width: 112, height: 130, alignItems: 'center', borderWidth: 2, borderColor: palette.ink,
    borderRadius: 17, backgroundColor: '#FFFDF8', paddingHorizontal: 8, paddingTop: 9,
  },
  machinePanel: { width: '100%', height: 25, flexDirection: 'row', alignItems: 'center', gap: 5, borderBottomWidth: 2, borderColor: palette.line, paddingBottom: 6 },
  machineDial: { width: 18, height: 18, justifyContent: 'center', alignItems: 'center', borderRadius: 9, borderWidth: 2, borderColor: palette.ink },
  machineDialDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: palette.accent },
  machineDisplay: { flex: 1, height: 16, justifyContent: 'center', gap: 3, paddingHorizontal: 4, borderRadius: 4, backgroundColor: palette.aqua },
  displayLine: { width: '85%', height: 2, borderRadius: 1, backgroundColor: palette.ink },
  displayShort: { width: '48%' },
  machineButton: { width: 9, height: 9, borderRadius: 5, backgroundColor: palette.coral, borderWidth: 1, borderColor: palette.ink },
  machineDoorOuter: {
    width: 77, height: 77, marginTop: 9, justifyContent: 'center', alignItems: 'center',
    borderRadius: 40, borderWidth: 4, borderColor: palette.ink, backgroundColor: palette.lilac,
  },
  machineDoorInner: {
    width: 60, height: 60, justifyContent: 'center', alignItems: 'center', overflow: 'hidden',
    borderRadius: 32, borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.accentWash,
  },
  machineBubbleOne: { position: 'absolute', width: 8, height: 8, right: 9, top: 11, borderRadius: 4, backgroundColor: palette.surface },
  machineBubbleTwo: { position: 'absolute', width: 5, height: 5, right: 17, top: 6, borderRadius: 3, backgroundColor: palette.surface },
  machineFootLeft: { position: 'absolute', left: 18, bottom: -3, width: 12, height: 5, borderRadius: 2, backgroundColor: palette.ink },
  machineFootRight: { position: 'absolute', right: 18, bottom: -3, width: 12, height: 5, borderRadius: 2, backgroundColor: palette.ink },
  tinyWasher: { width: 30, height: 36, borderWidth: 1.5, borderColor: palette.ink, borderRadius: 5, backgroundColor: '#FFFDF8', paddingHorizontal: 3, paddingTop: 3, alignItems: 'center' },
  tinyPanel: { width: '100%', height: 6, flexDirection: 'row', alignItems: 'center', gap: 2, borderBottomWidth: 1, borderColor: palette.line, paddingBottom: 2 },
  tinyDial: { width: 4, height: 4, borderRadius: 2, backgroundColor: palette.coral, borderWidth: 0.5, borderColor: palette.ink },
  tinyDisplay: { flex: 1, height: 3, borderRadius: 1, backgroundColor: palette.aqua },
  tinyDoor: { width: 18, height: 18, marginTop: 3, borderRadius: 10, borderWidth: 1.5, borderColor: palette.ink, backgroundColor: palette.lilac },
  shortcuts: { flexGrow: 1, minHeight: 286, maxHeight: 390, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignContent: 'stretch', rowGap: 10 },
  shortcut: {
    width: '48.5%', minHeight: 138, maxHeight: 190, flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    gap: 8, paddingHorizontal: 12, paddingVertical: 14, borderWidth: 1.5, borderColor: palette.ink, borderRadius: 20,
  },
  shortcutGlyph: {
    width: 56, height: 56, alignItems: 'center', justifyContent: 'center',
    borderRadius: 19, borderWidth: 1.5, borderColor: palette.ink, backgroundColor: 'rgba(255,255,255,0.48)',
  },
  shortcutTitle: { color: palette.ink, fontSize: 15, lineHeight: 20, fontWeight: '800', textAlign: 'center' },
});
