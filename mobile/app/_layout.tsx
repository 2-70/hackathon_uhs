// Lucian UX/UI Prompt #041 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#041
// Lucian UX/UI Prompt #332 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#332
import Ionicons from '@expo/vector-icons/Ionicons';
import { BlurView } from 'expo-blur';
import { Slot, usePathname, useRouter, type Href } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { LaundryProvider } from '../src/store';
import { palette, ScreenHeader, styles, type IconName } from '../src/ui';

const tabs: { href: Href; name: string; icon: IconName; selected: IconName }[] = [
  { href: '/', name: '홈', icon: 'home-outline', selected: 'home' },
  { href: '/wardrobe', name: '옷장', icon: 'shirt-outline', selected: 'shirt' },
  { href: '/machines', name: '세탁기', icon: 'options-outline', selected: 'options' },
  { href: '/drum', name: '드럼', icon: 'disc-outline', selected: 'disc' },
];

export default function Layout() {
  return (
    <SafeAreaProvider>
      <LaundryProvider>
        <AppShell />
      </LaundryProvider>
    </SafeAreaProvider>
  );
}

function AppShell() {
  const pathname = usePathname();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const isEditor = pathname === '/garment';
  const routeTitle = pathname === '/'
    ? '오늘의 세탁'
    : pathname === '/machines'
      ? '우리 집 세탁기'
        : undefined;

  return (
    <SafeAreaView
      edges={isEditor ? ['top', 'left', 'right', 'bottom'] : ['top', 'left', 'right']}
      style={layout.shell}
    >
      <StatusBar style="dark" />

      {(routeTitle || pathname === '/drum') && (
        <ScreenHeader
          title={routeTitle}
          onBack={pathname === '/' ? undefined : () => router.canGoBack() ? router.back() : router.replace('/')}
        />
      )}

      <View style={layout.page}>
        <View style={layout.route}><Slot /></View>
      </View>

      {!isEditor && (
        <View style={[layout.tabBar, { paddingBottom: insets.bottom + 10 }]}>
          <View style={layout.dockShadow}>
            <View style={layout.dockSurface}>
              <BlurView intensity={18} tint="light" pointerEvents="none" style={layout.dockBlur} />
              <View style={layout.tabs}>
                {tabs.map((tab) => renderTab(tab))}
              </View>
            </View>
          </View>
        </View>
      )}
    </SafeAreaView>
  );

  function renderTab(tab: (typeof tabs)[number]) {
    const active = pathname === tab.href;
    return (
      <Pressable
        key={tab.name}
        accessibilityRole="tab"
        accessibilityLabel={tab.name}
        accessibilityState={{ selected: active }}
        onPress={() => { if (!active) router.replace(tab.href); }}
        style={({ pressed }) => [layout.tab, active && layout.activeTab, pressed && styles.dimmed]}
      >
        <Ionicons name={active ? tab.selected : tab.icon} size={21} color={active ? palette.accent : palette.muted} />
        <Text style={[layout.tabLabel, active && layout.activeTabLabel]}>{tab.name}</Text>
      </Pressable>
    );
  }
}

const layout = StyleSheet.create({
  shell: { flex: 1, backgroundColor: palette.paper },
  page: { flex: 1, backgroundColor: palette.paper },
  route: { flex: 1, backgroundColor: palette.paper },
  tabBar: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingTop: 6, paddingHorizontal: 14, zIndex: 2 },
  dockShadow: {
    width: '100%', maxWidth: 360, height: 66, alignSelf: 'center', borderRadius: 22,
    shadowColor: palette.navy, shadowOpacity: 0.10, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 7,
  },
  dockSurface: {
    flex: 1, overflow: 'hidden', borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.94)',
  },
  dockBlur: { ...StyleSheet.absoluteFill, borderRadius: 22 },
  tabs: { flex: 1, width: '100%', alignSelf: 'center', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 4, paddingHorizontal: 8 },
  tab: { flex: 1, minWidth: 0, height: 52, borderRadius: 15, justifyContent: 'center', alignItems: 'center', gap: 1 },
  activeTab: { backgroundColor: palette.accentWash },
  tabLabel: { color: palette.muted, fontSize: 10, lineHeight: 13, fontWeight: '700' },
  activeTabLabel: { color: palette.accent, fontWeight: '800' },
});
