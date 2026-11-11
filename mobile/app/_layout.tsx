// Lucian UX/UI Prompt #041 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#041
// Lucian UX/UI Prompt #332 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#332
import Ionicons from '@expo/vector-icons/Ionicons';
import { BlurView } from 'expo-blur';
import { Slot, usePathname, useRouter, type Href } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { LaundryProvider } from '../src/store';
import { LaundryRouteHeader, palette, ScreenHeader, SpringPressable, styles, type IconName } from '../src/ui';

const tabs: { href: Href; name: string; icon: IconName; selected: IconName; group?: 'laundry' }[] = [
  { href: '/drum', name: '세탁', icon: 'disc-outline', selected: 'disc', group: 'laundry' },
  { href: '/', name: '홈', icon: 'home-outline', selected: 'home' },
  { href: '/wardrobe', name: '옷장', icon: 'shirt-outline', selected: 'shirt' },
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
  const isLaundry = pathname === '/drum' || pathname === '/machines';
  const routeTitle = pathname === '/' ? '오늘의 세탁' : undefined;

  return (
    <SafeAreaView
      edges={isEditor ? ['top', 'left', 'right', 'bottom'] : ['top', 'left', 'right']}
      style={layout.shell}
    >
      <StatusBar style="dark" />

      {isLaundry ? (
        <LaundryRouteHeader
          active={pathname === '/machines' ? 'machines' : 'drum'}
          onBack={() => router.canGoBack() ? router.back() : router.replace('/')}
          onNavigate={(route) => router.replace(route)}
        />
      ) : routeTitle ? (
        <ScreenHeader title={routeTitle} />
      ) : null}

      <View style={layout.page}>
        <View style={layout.route}><Slot /></View>
      </View>

      {!isEditor && (
        <View style={[layout.tabBar, { paddingBottom: insets.bottom + 10 }]}>
          <View style={layout.dockShadow}>
            <View style={layout.dockSurface}>
              <BlurView intensity={18} tint="light" pointerEvents="none" style={layout.dockBlur} />
              <View accessibilityRole="tablist" accessibilityLabel="하단 메뉴" style={layout.tabs}>
                {tabs.map((tab) => renderTab(tab))}
              </View>
            </View>
          </View>
        </View>
      )}
    </SafeAreaView>
  );

  function renderTab(tab: (typeof tabs)[number]) {
    const active = tab.group === 'laundry' ? isLaundry : pathname === tab.href;
    return (
      <SpringPressable
        key={tab.name}
        accessibilityRole="tab"
        accessibilityLabel={tab.name}
        accessibilityState={{ selected: active }}
        onPress={() => {
          if (!active) {
            router.replace(tab.href);
          }
        }}
        style={({ pressed }) => [
          layout.tab,
          active && tab.group !== 'laundry' && layout.activeTab,
          pressed && styles.dimmed,
        ]}
      >
        <Ionicons name={active ? tab.selected : tab.icon} size={21} color={active ? palette.accent : palette.muted} />
        <Text style={[layout.tabLabel, active && layout.activeTabLabel]}>{tab.name}</Text>
      </SpringPressable>
    );
  }
}

const layout = StyleSheet.create({
  shell: { flex: 1, backgroundColor: palette.paper },
  page: { flex: 1, backgroundColor: palette.paper },
  route: { flex: 1, backgroundColor: palette.paper },
  tabBar: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingTop: 6, paddingHorizontal: 14, zIndex: 2 },
  dockShadow: {
    width: '100%', maxWidth: 360, height: 72, alignSelf: 'center', borderRadius: 24,
    shadowColor: palette.navy, shadowOpacity: 0.10, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 7,
  },
  dockSurface: {
    flex: 1, overflow: 'hidden', borderRadius: 24, borderWidth: 1, borderColor: palette.line,
    backgroundColor: 'rgba(255,254,255,0.94)',
  },
  dockBlur: { ...StyleSheet.absoluteFill, borderRadius: 24 },
  tabs: { flex: 1, width: '100%', alignSelf: 'center', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 4, paddingHorizontal: 11 },
  tab: { flex: 1, minWidth: 0, height: 56, borderRadius: 15, justifyContent: 'center', alignItems: 'center', gap: 2 },
  activeTab: { backgroundColor: palette.accentWash },
  tabLabel: { color: palette.muted, fontSize: 10, lineHeight: 13, fontWeight: '700' },
  activeTabLabel: { color: palette.accent, fontWeight: '800' },
});
