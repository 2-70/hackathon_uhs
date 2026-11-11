import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter, type Href } from 'expo-router';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { Garment } from '../src/model';
import { basketLimit, useLaundry } from '../src/store';
import { Notice, palette, styles, type IconName } from '../src/ui';

type TileItem = {
  title: string;
  detail: string;
  action: string;
  icon: IconName;
  color: string;
  href: Href;
};

export default function Home() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { ready, loadError, garments, basketIds, machine, analysisStarted } = useLaundry();
  const hasData = ready && !loadError;
  const count = basketIds.length;
  // New garments are prepended by saveGarment; keep the store's newest-first order.
  const recentGarments = hasData ? garments.slice(0, 2) : [];
  const canAnalyze = count > 0 && !!machine;
  const planHref: Href = canAnalyze && analysisStarted
    ? { pathname: '/drum', params: { focus: 'plan' } }
    : '/drum';
  const next: { href: Href; label: string } = count === 0
    ? { href: '/wardrobe', label: '옷 골라 담기' }
    : machine
      ? { href: planHref, label: analysisStarted ? '세탁 계획 보기' : '세탁 계획 만들기' }
      : { href: '/machines', label: '세탁기 등록하기' };
  const tiles: TileItem[] = [
    {
      title: '의류 등록',
      detail: '사진이나 라벨로 세탁 정보 추가',
      action: '새 의류 등록',
      icon: 'add',
      color: palette.peach,
      href: '/garment',
    },
    {
      title: '내 옷장',
      detail: hasData ? `등록 의류 ${garments.length}벌` : loadError ? '저장 상태를 확인해 주세요' : '옷장을 불러오는 중',
      action: '옷장 열기',
      icon: 'shirt-outline',
      color: palette.lilac,
      href: '/wardrobe',
    },
    {
      title: '세탁기',
      detail: machine ? machine.model : hasData ? '등록된 모델이 없어요' : loadError ? '저장 상태 확인 필요' : '세탁기 상태 확인 중',
      action: machine ? '기기 정보 보기' : '모델 선택하기',
      icon: 'options-outline',
      color: palette.aqua,
      href: '/machines',
    },
    {
      title: '세탁 계획',
      detail: analysisStarted && canAnalyze
        ? '분석 결과와 세탁 안내 보기'
        : count === 0
          ? '드럼에 의류를 담아 주세요'
          : machine
            ? '담은 의류를 분석해 보세요'
            : '세탁기를 등록해 주세요',
      action: analysisStarted && canAnalyze ? '결과 보기' : '계획 준비하기',
      icon: 'list-outline',
      color: palette.coral,
      href: planHref,
    },
  ];

  return (
    <ScrollView
      style={home.screen}
      contentContainerStyle={[home.content, { paddingBottom: 118 + insets.bottom }]}
      showsVerticalScrollIndicator={false}
    >
      <View style={home.heading}>
        <View style={home.greeting}>
          <View style={home.avatar} importantForAccessibility="no-hide-descendants">
            <Ionicons name="person-outline" size={22} color={palette.accent} />
          </View>
          <View style={home.greetingCopy}>
            <Text style={home.hello}>안녕하세요</Text>
            <Text accessibilityRole="header" style={home.title}>오늘의 세탁</Text>
          </View>
        </View>
        <View style={home.headerActions}>
          <HeaderAction icon="disc-outline" label="드럼" onPress={() => router.push('/drum')} />
          <HeaderAction icon="add" label="의류 등록" onPress={() => router.push('/garment')} />
        </View>
      </View>

      {loadError && <Notice tone="error">{loadError}</Notice>}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`세탁 준비, ${ready ? next.label : '옷장을 불러오는 중'}`}
        accessibilityState={{ disabled: !ready || !!loadError }}
        disabled={!ready || !!loadError}
        onPress={() => router.push(next.href)}
        style={({ pressed }) => [home.drumCard, (pressed || !ready || !!loadError) && styles.dimmed]}
      >
        <View style={home.drumHeading}>
          <View style={home.cardIcon} importantForAccessibility="no-hide-descendants">
            <Ionicons name="disc-outline" size={20} color={palette.navy} />
          </View>
          <View style={home.drumHeadingCopy}>
            <Text style={home.drumTitle}>드럼 현황</Text>
            <Text style={home.drumSummary} numberOfLines={1}>
              {hasData
                ? (count > 0 ? `의류 ${count}벌이 담겨 있어요` : '세탁할 옷을 골라 담아 주세요')
                : loadError ? '저장한 옷장을 불러오지 못했어요' : '옷장을 불러오는 중'}
            </Text>
          </View>
          <View style={home.capacityBadge}>
            <Text style={home.capacityText}>최대 {basketLimit}벌</Text>
          </View>
        </View>

        <View style={home.metrics}>
          <Metric label="옷장" value={hasData ? `${garments.length}벌` : '–'} />
          <Metric label="담은 옷" value={hasData ? `${count}벌` : '–'} />
          <Metric label="남은 자리" value={hasData ? `${Math.max(0, basketLimit - count)}벌` : '–'} />
          <Metric label="세탁기" value={!hasData ? '–' : machine?.model ?? '미등록'} compact />
        </View>

        <View style={home.cta}>
          <Text style={home.ctaLabel} numberOfLines={1}>
            {!ready ? '옷장을 불러오는 중' : loadError ? '저장 상태를 확인해 주세요' : next.label}
          </Text>
          <Ionicons name="arrow-forward" size={18} color={palette.ink} />
        </View>
      </Pressable>

      <View style={home.tiles}>
        {tiles.map((tile) => (
          <FeatureTile key={tile.title} item={tile} onPress={() => router.push(tile.href)} />
        ))}
      </View>

      {recentGarments.length > 0 && (
        <View style={home.recentSection}>
          <Text accessibilityRole="header" style={home.recentTitle}>최근 등록한 옷</Text>
          <View style={home.recentList}>
            {recentGarments.map((garment) => (
              <RecentGarment
                key={garment.id}
                garment={garment}
                onPress={() => router.push({ pathname: '/garment', params: { id: garment.id } })}
              />
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
}

function HeaderAction({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [home.headerAction, pressed && styles.dimmed]}
    >
      <Ionicons name={icon} size={20} color={palette.ink} />
    </Pressable>
  );
}

function Metric({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
  return (
    <View style={[home.metric, compact && home.compactMetric]}>
      <Text style={home.metricLabel} numberOfLines={1}>{label}</Text>
      <Text
        style={[home.metricValue, compact && home.compactMetricValue]}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.72}
      >
        {value}
      </Text>
    </View>
  );
}

function FeatureTile({ item, onPress }: { item: TileItem; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.title}, ${item.detail}, ${item.action}`}
      onPress={onPress}
      style={({ pressed }) => [home.tile, { backgroundColor: item.color }, pressed && styles.dimmed]}
    >
      <View style={home.tileHeader}>
        <Text style={home.tileTitle}>{item.title}</Text>
        <View style={home.tileIcon} importantForAccessibility="no-hide-descendants">
          <Ionicons name={item.icon} size={17} color={palette.ink} />
        </View>
      </View>
      <Text style={home.tileDetail} numberOfLines={2}>{item.detail}</Text>
      <View style={home.tileAction}>
        <Text style={home.tileActionText} numberOfLines={1}>{item.action}</Text>
        <Ionicons name="arrow-forward" size={16} color={palette.ink} />
      </View>
    </Pressable>
  );
}

function RecentGarment({ garment, onPress }: { garment: Garment; onPress: () => void }) {
  const attribute = [garment.category, garment.color, garment.material].find((value) => value.trim())
    ?? (garment.maxTemp !== null ? `최대 ${garment.maxTemp}°C` : '세탁 정보 확인 필요');
  const icon: IconName = garment.category.includes('바지') ? 'pricetag-outline' : 'shirt-outline';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${garment.name}, ${attribute}, 의류 정보 수정`}
      onPress={onPress}
      style={({ pressed }) => [home.recentCard, pressed && styles.dimmed]}
    >
      {garment.photo ? (
        <Image accessibilityLabel={`${garment.name} 사진`} source={{ uri: garment.photo }} style={home.recentThumb} />
      ) : (
        <View style={home.recentThumb} importantForAccessibility="no-hide-descendants">
          <Ionicons name={icon} size={20} color={palette.accent} />
        </View>
      )}
      <View style={home.recentCopy}>
        <Text style={home.recentName} numberOfLines={1}>{garment.name}</Text>
        <Text style={home.recentAttribute} numberOfLines={1}>{attribute}</Text>
      </View>
      <Ionicons name="chevron-forward" size={15} color={palette.muted} />
    </Pressable>
  );
}

const home = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.paper },
  content: {
    width: '100%', maxWidth: 620, alignSelf: 'center',
    paddingHorizontal: 20, paddingTop: 11, paddingBottom: 25, gap: 13,
  },
  heading: { minHeight: 52, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  greeting: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 10 },
  avatar: {
    width: 44, height: 44, flexShrink: 0, alignItems: 'center', justifyContent: 'center',
    borderRadius: 22, backgroundColor: palette.accentWash,
  },
  greetingCopy: { flex: 1, minWidth: 0, gap: 1 },
  hello: { color: palette.muted, fontSize: 11, lineHeight: 15, fontWeight: '600' },
  title: { color: palette.ink, fontSize: 21, lineHeight: 27, letterSpacing: -0.55, fontWeight: '800' },
  headerActions: { flexDirection: 'row', gap: 7 },
  headerAction: {
    width: 40, height: 40, alignItems: 'center', justifyContent: 'center',
    borderRadius: 20, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface,
  },
  drumCard: {
    gap: 11, padding: 14, borderRadius: 23,
    borderWidth: 1, borderColor: palette.blush, backgroundColor: palette.blush,
  },
  drumHeading: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  cardIcon: {
    width: 36, height: 36, alignItems: 'center', justifyContent: 'center',
    borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.58)',
  },
  drumHeadingCopy: { flex: 1, minWidth: 0, gap: 2 },
  drumTitle: { color: palette.ink, fontSize: 15, lineHeight: 19, fontWeight: '800' },
  drumSummary: { color: palette.navy, fontSize: 11, lineHeight: 15, fontWeight: '600' },
  capacityBadge: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: 11, backgroundColor: 'rgba(255,255,255,0.62)' },
  capacityText: { color: palette.navy, fontSize: 10, fontWeight: '700' },
  metrics: {
    flexDirection: 'row', alignItems: 'stretch', gap: 5,
    paddingVertical: 9, paddingHorizontal: 2,
    borderTopWidth: 1, borderBottomWidth: 1, borderColor: 'rgba(36,37,57,0.11)',
  },
  metric: { flex: 1, minWidth: 0, alignItems: 'center', justifyContent: 'center', gap: 3 },
  compactMetric: { flex: 1.35 },
  metricLabel: { color: palette.navy, opacity: 0.72, fontSize: 9, lineHeight: 12, fontWeight: '600' },
  metricValue: { color: palette.ink, fontSize: 15, lineHeight: 19, fontWeight: '800', fontVariant: ['tabular-nums'] },
  compactMetricValue: { fontSize: 11 },
  cta: {
    minHeight: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8,
    paddingTop: 8, borderTopWidth: 1, borderColor: 'rgba(36,37,57,0.11)',
  },
  ctaLabel: { flex: 1, color: palette.ink, fontSize: 13, fontWeight: '800' },
  tiles: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 10 },
  tile: {
    width: '48.5%', minHeight: 164, justifyContent: 'space-between', gap: 9,
    padding: 12, borderRadius: 21,
  },
  tileHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 },
  tileTitle: { flex: 1, color: palette.ink, fontSize: 14, lineHeight: 18, fontWeight: '800' },
  tileIcon: {
    width: 30, height: 30, alignItems: 'center', justifyContent: 'center',
    borderRadius: 11, backgroundColor: 'rgba(255,255,255,0.67)',
  },
  tileDetail: { minHeight: 32, color: palette.navy, fontSize: 11, lineHeight: 16, fontWeight: '600' },
  tileAction: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 5 },
  tileActionText: { flex: 1, color: palette.ink, fontSize: 11, lineHeight: 15, fontWeight: '800' },
  recentSection: { gap: 9 },
  recentTitle: { color: palette.ink, fontSize: 16, lineHeight: 21, fontWeight: '800', letterSpacing: -0.25 },
  recentList: { flexDirection: 'row', justifyContent: 'space-between', gap: 9 },
  recentCard: {
    flex: 1, minWidth: 0, minHeight: 72, flexDirection: 'row', alignItems: 'center', gap: 7,
    padding: 8, borderRadius: 16, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface,
  },
  recentThumb: {
    width: 42, height: 42, flexShrink: 0, alignItems: 'center', justifyContent: 'center',
    borderRadius: 12, backgroundColor: palette.accentWash, resizeMode: 'cover',
  },
  recentCopy: { flex: 1, minWidth: 0, gap: 3 },
  recentName: { color: palette.ink, fontSize: 12, lineHeight: 16, fontWeight: '800' },
  recentAttribute: { color: palette.muted, fontSize: 10, lineHeight: 14, fontWeight: '600' },
});
