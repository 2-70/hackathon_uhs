import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { searchMachines } from '../src/api';
import type { Machine } from '../src/model';
import { useLaundry } from '../src/store';
import { Button, Notice, Screen, palette, styles } from '../src/ui';

type SearchResult =
  | { query: string; status: 'loading' | 'error' }
  | { query: string; status: 'ready'; machines: Machine[] };

export default function MachinesScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { machine, ready, loadError, registerMachine } = useLaundry();
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<SearchResult>({ query: '', status: 'loading' });
  const [searchAttempt, setSearchAttempt] = useState(0);
  const [selected, setSelected] = useState<Machine | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  useEffect(() => {
    let active = true;
    searchMachines(query).then(
      (machines) => {
        if (active) setResult({ query, status: 'ready', machines });
      },
      () => {
        if (active) setResult({ query, status: 'error' });
      },
    );
    return () => { active = false; };
  }, [query, searchAttempt]);

  const matches = result.query === query && result.status === 'ready' ? result.machines : [];
  const preview = selected ?? machine;
  const isRegistered = preview !== null && preview.id === machine?.id;

  async function save(candidate: Machine) {
    if (saving) return;
    setSaving(true);
    setSaveError(false);
    try {
      await registerMachine(candidate);
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={local.screen}>
      <Screen>
        <View style={local.pageHeader}>
          <Text accessibilityRole="header" style={local.pageTitle}>우리 집 세탁기</Text>
        </View>
        {loadError && <Notice tone="error">{loadError}</Notice>}
        <View style={local.active}>
          <View style={local.activeIcon}>
            <Ionicons name="disc-outline" size={23} color={palette.accent} />
          </View>
          <View style={local.activeDetail}>
            <Text style={local.label}>등록 모델</Text>
            <Text style={local.activeValue}>{!ready ? '불러오는 중…' : machine?.model ?? '미등록'}</Text>
            {machine && <Text style={local.metadata}>{machine.maker}</Text>}
          </View>
          {machine && (
            <View style={local.stat}>
              <Text style={local.statValue}>{machine.courses.length}</Text>
              <Text style={local.statLabel}>지원 코스</Text>
            </View>
          )}
        </View>

        <View style={local.section}>
          <Text accessibilityRole="header" style={styles.title}>모델 검색</Text>
          <View style={local.search}>
            <Ionicons name="search-outline" size={19} color={palette.accent} />
            <TextInput
              accessibilityLabel="제조사 또는 모델명"
              value={query}
              onChangeText={setQuery}
              placeholder="제조사 또는 모델명"
              placeholderTextColor={palette.muted}
              autoCapitalize="none"
              autoCorrect={false}
              style={local.input}
            />
            {query.length > 0 && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="검색어 지우기"
                onPress={() => setQuery('')}
                style={local.iconButton}
              >
                <Ionicons name="close" size={19} color={palette.muted} />
              </Pressable>
            )}
          </View>

          {result.query !== query || result.status === 'loading' ? (
            <Notice>모델을 찾는 중이에요.</Notice>
          ) : result.status === 'error' ? (
            <View style={local.feedback}>
              <Notice tone="error">모델 목록을 불러오지 못했어요.</Notice>
              <Button tone="secondary" onPress={() => {
                setResult({ query, status: 'loading' });
                setSearchAttempt((attempt) => attempt + 1);
              }}>다시 검색</Button>
            </View>
          ) : matches.length === 0 ? (
            <View style={local.feedback}>
              <Text style={styles.title}>일치하는 세탁기 모델이 없어요</Text>
              <Text style={styles.muted}>모델명의 일부만 입력해 보세요.</Text>
              {query.length > 0 && <Button tone="secondary" onPress={() => setQuery('')}>검색어 지우기</Button>}
            </View>
          ) : (
            <View accessibilityRole="radiogroup">
              <View style={local.listHeader}>
                <Text style={local.label}>등록 모델 {matches.length}개</Text>
              </View>
              {matches.map((candidate, index) => {
                const checked = candidate.id === preview?.id;
                return (
                  <Pressable
                    key={candidate.id}
                    accessibilityRole="radio"
                    accessibilityState={{ checked, disabled: saving }}
                    disabled={saving}
                    onPress={() => {
                      setSelected(candidate);
                      setSaveError(false);
                    }}
                    style={({ pressed }) => [
                      local.result, index > 0 && local.resultDivider, checked && local.selected, pressed && styles.dimmed,
                    ]}
                  >
                    <View style={[local.radio, checked && local.radioChecked]}>
                      {checked && <View style={local.radioDot} />}
                    </View>
                    <View style={local.modelDetail}>
                      <Text style={local.model}>{candidate.model}</Text>
                      <Text style={local.metadata}>{candidate.maker} · 코스 {candidate.courses.length}개</Text>
                    </View>
                    {candidate.id === machine?.id && (
                      <View style={local.inUseBadge}>
                        <Text style={local.inUse}>등록됨</Text>
                      </View>
                    )}
                  </Pressable>
                );
              })}
            </View>
          )}
        </View>

        {preview && (
          <View style={local.section}>
            <View style={local.tableTitle}>
              <Text accessibilityRole="header" style={styles.title}>지원 코스</Text>
              <Text style={local.label}>{preview.model}</Text>
            </View>
            <View style={local.table}>
              <View style={[local.tableRow, local.tableHeader]}>
                <Text style={[local.label, local.courseCell]}>코스</Text>
                <Text style={[local.label, local.numberCell]}>물온도</Text>
                <Text style={[local.label, local.numberCell]}>탈수</Text>
              </View>
              {preview.courses.map((course, courseIndex) => (
                <View key={course.id} style={courseIndex > 0 && local.courseDivider}>
                  {(course.verifiedSettings ?? []).map(({ id, temperature, spin }, index) => (
                    <View
                      key={id}
                      accessible
                      accessibilityLabel={`${course.name}, 물온도 ${temperature}, 탈수 ${spin}`}
                      style={[local.tableRow, index > 0 && local.continuationRow]}
                    >
                      <Text style={[local.tableValue, local.courseCell]}>
                        {index === 0 ? course.name : ''}
                      </Text>
                      <Text style={[local.tableValue, local.numberCell, local.numeric]}>{temperature}</Text>
                      <Text style={[local.tableValue, local.numberCell, local.numeric]}>{spin}</Text>
                    </View>
                  ))}
                </View>
              ))}
            </View>
          </View>
        )}
      </Screen>

      {preview && (
        <View style={[local.dock, { marginBottom: 98 + insets.bottom }]}>
          {saveError && <Notice tone="error">세탁기를 저장하지 못했어요. 다시 시도해 주세요.</Notice>}
          <View style={local.dockRow}>
            <View style={local.dockModel}>
              <Text style={local.label}>{isRegistered ? '등록 모델' : '선택한 모델'}</Text>
              <Text style={local.model}>{preview.model}</Text>
            </View>
            {isRegistered ? (
              <Button icon="arrow-forward" onPress={() => router.replace('/drum')}>드럼으로 이동</Button>
            ) : (
              <Button
                icon="checkmark"
                onPress={() => void save(preview)}
                disabled={!ready || !!loadError || saving}
              >
                {saving ? '저장 중…' : machine ? '모델 변경' : '모델 등록'}
              </Button>
            )}
          </View>
        </View>
      )}
    </View>
  );
}

const local = StyleSheet.create({
  screen: { flex: 1 },
  pageHeader: { alignItems: 'center', paddingVertical: 1 },
  pageTitle: { color: palette.ink, fontSize: 21, lineHeight: 28, fontWeight: '800', letterSpacing: -0.45, textAlign: 'center' },
  active: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 13,
    borderWidth: 1, borderColor: palette.line, borderRadius: 17, backgroundColor: palette.surface,
  },
  activeIcon: {
    width: 42, height: 42, borderRadius: 13, backgroundColor: palette.accentWash,
    alignItems: 'center', justifyContent: 'center',
  },
  activeDetail: { flex: 1, gap: 3 },
  activeValue: { color: palette.ink, fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] },
  label: { color: palette.muted, fontSize: 12, fontWeight: '700' },
  stat: {
    alignItems: 'center', gap: 2, paddingVertical: 7, paddingHorizontal: 9,
    backgroundColor: palette.aqua, borderRadius: 13,
  },
  statValue: { color: palette.accent, fontSize: 17, fontWeight: '800', fontVariant: ['tabular-nums'] },
  statLabel: { color: palette.muted, fontSize: 11, fontWeight: '700' },
  section: { gap: 11, padding: 14, borderRadius: 17, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface },
  search: {
    flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 48,
    paddingLeft: 12, borderWidth: 1, borderColor: palette.line, borderRadius: 13, backgroundColor: palette.paper,
  },
  input: { flex: 1, minWidth: 0, color: palette.ink, fontSize: 15, paddingRight: 4 },
  iconButton: { width: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  feedback: { alignItems: 'flex-start', gap: 8, paddingVertical: 8 },
  listHeader: { paddingVertical: 7, paddingHorizontal: 3 },
  result: {
    flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 60, paddingHorizontal: 9,
    paddingVertical: 8, borderRadius: 12,
  },
  resultDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: palette.line },
  selected: { backgroundColor: palette.accentWash },
  radio: {
    width: 18, height: 18, borderRadius: 9, borderWidth: 1, borderColor: palette.muted,
    alignItems: 'center', justifyContent: 'center',
  },
  radioChecked: { borderColor: palette.accent },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: palette.accent },
  modelDetail: { flex: 1, gap: 3 },
  model: { color: palette.ink, fontSize: 15, fontWeight: '700', fontVariant: ['tabular-nums'] },
  metadata: { color: palette.muted, fontSize: 12, lineHeight: 16 },
  inUseBadge: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 9, backgroundColor: palette.aqua },
  inUse: { color: palette.accent, fontSize: 12, fontWeight: '700' },
  tableTitle: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 },
  table: { borderRadius: 12, borderWidth: 1, borderColor: palette.line, overflow: 'hidden' },
  tableRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 9, paddingVertical: 9 },
  tableHeader: { backgroundColor: palette.subtle },
  courseDivider: { borderTopWidth: 1, borderTopColor: palette.line },
  continuationRow: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: palette.line },
  courseCell: { flex: 1.3 },
  numberCell: { flex: 0.8, textAlign: 'right' },
  tableValue: { color: palette.ink, fontSize: 14, fontWeight: '600' },
  numeric: { fontVariant: ['tabular-nums'] },
  dock: {
    width: '100%', maxWidth: 640, alignSelf: 'center', gap: 7, paddingHorizontal: 18, paddingVertical: 10,
    backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.line, borderRadius: 18,
    shadowColor: palette.ink, shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 4,
  },
  dockRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  dockModel: { gap: 3 },
});
