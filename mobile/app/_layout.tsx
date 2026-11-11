// Lucian UX/UI Prompt #041 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#041
// Lucian UX/UI Prompt #332 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#332
import Ionicons from '@expo/vector-icons/Ionicons';
import { BlurView } from 'expo-blur';
import { Slot, usePathname, useRouter, type Href } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { LaundryProvider } from '../src/store';
import { palette, styles, type IconName } from '../src/ui';

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
  const showBack = pathname !== '/' && pathname !== '/wardrobe';

  return (
    <SafeAreaView
      edges={isEditor ? ['top', 'left', 'right', 'bottom'] : ['top', 'left', 'right']}
      style={layout.shell}
    >
      <StatusBar style="dark" />

      {showBack && (
        <View style={layout.detailBar}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            style={({ pressed }) => [layout.back, pressed && styles.dimmed]}
            onPress={() => router.canGoBack() ? router.back() : router.replace('/')}
          >
            <Ionicons name="chevron-back" size={22} color={palette.ink} />
          </Pressable>
          <Text style={layout.mode}>의류 관리</Text>
        </View>
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
                {tabs.slice(0, 2).map((tab) => renderTab(tab))}
                <View style={layout.addSlot}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="의류 등록"
                    onPress={() => router.push('/garment')}
                    style={({ pressed }) => [layout.cell, pressed && styles.dimmed]}
                  >
                    <Ionicons name="add" size={25} color={palette.ink} />
                  </Pressable>
                </View>
                {tabs.slice(2).map((tab) => renderTab(tab))}
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
        <Ionicons name={active ? tab.selected : tab.icon} size={22} color={palette.ink} />
      </Pressable>
    );
  }
}

const layout = StyleSheet.create({
  shell: { flex: 1, backgroundColor: palette.paper },
  detailBar: { minHeight: 47, width: '100%', maxWidth: 640, alignSelf: 'center', paddingHorizontal: 17, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  back: { minWidth: 44, height: 44, alignItems: 'flex-start', justifyContent: 'center', paddingLeft: 5 },
  mode: { color: palette.accent, backgroundColor: palette.accentWash, fontSize: 11, fontWeight: '700', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10 },
  page: { flex: 1, backgroundColor: palette.paper },
  route: { flex: 1, backgroundColor: palette.paper },
  tabBar: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingTop: 8, paddingHorizontal: 14, zIndex: 2 },
  dockShadow: {
    width: '100%', maxWidth: 330, height: 70, alignSelf: 'center', borderRadius: 25,
    shadowColor: palette.navy, shadowOpacity: 0.10, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 7,
  },
  dockSurface: {
    flex: 1, overflow: 'hidden', borderRadius: 25,
    backgroundColor: 'rgba(255,255,255,0.94)',
  },
  dockBlur: { ...StyleSheet.absoluteFill, borderRadius: 25 },
  tabs: { flex: 1, width: '100%', alignSelf: 'center', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingHorizontal: 10 },
  tab: { width: 48, height: 48, borderRadius: 15, justifyContent: 'center', alignItems: 'center', backgroundColor: palette.subtle },
  activeTab: { backgroundColor: palette.lilac },
  addSlot: { width: 48, alignItems: 'center', justifyContent: 'center' },
  cell: { width: 48, height: 48, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.subtle },
});
