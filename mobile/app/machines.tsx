import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { searchMachines } from '../src/mock';
import { LaundryLoading } from '../src/LaundryLoading';
import type { Machine } from '../src/model';
import { useLaundry } from '../src/store';
import { Button, Notice, Screen, SearchField, palette, styles } from '../src/ui';

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
        {loadError && <Notice tone="error">{loadError}</Notice>}
        <View style={[styles.card, styles.cardContent, local.active]}>
          <View style={styles.iconBadge}>
            <Ionicons name="water-outline" size={23} color={palette.accent} />
          </View>
          <View style={local.activeDetail}>
            <Text style={styles.rowMeta}>내 세탁기</Text>
            <Text style={styles.rowTitle}>{!ready ? '불러오는 중…' : machine?.model ?? '미등록'}</Text>
            {machine && <Text style={styles.rowMeta}>{machine.maker}</Text>}
          </View>
          {machine && (
            <View style={local.registeredBadge}>
              <Ionicons name="checkmark-circle" size={15} color={palette.accent} />
              <Text style={local.registeredText}>등록됨</Text>
            </View>
          )}
        </View>

        <View style={[styles.card, styles.cardContent, local.section]}>
          <Text accessibilityRole="header" style={styles.title}>모델 검색</Text>
          <SearchField
            label="제조사 또는 모델명"
            value={query}
            onChangeText={setQuery}
            placeholder="제조사 또는 모델명"
            autoCapitalize="none"
            autoCorrect={false}
          />

          {result.query !== query || result.status === 'loading' ? (
            <LaundryLoading compact label="모델을 찾는 중이에요." />
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
              <Text style={styles.title}>일치하는 샘플 모델이 없어요</Text>
              <Text style={styles.muted}>모델명의 일부만 입력해 보세요.</Text>
              {query.length > 0 && <Button tone="secondary" onPress={() => setQuery('')}>검색어 지우기</Button>}
            </View>
          ) : (
            <View accessibilityRole="radiogroup">
              <View style={local.listHeader}>
                <Text style={local.label}>샘플 모델 {matches.length}개</Text>
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
                      <Text style={styles.rowTitle}>{candidate.model}</Text>
                      <Text style={styles.rowMeta}>{candidate.maker} · 코스 {candidate.courses.length}개</Text>
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
          <View style={[styles.card, styles.cardContent, local.section]}>
            <View style={local.tableTitle}>
              <Text accessibilityRole="header" style={styles.title}>지원 코스</Text>
              <Text style={local.label}>{preview.model}</Text>
            </View>
            <View style={local.table}>
              <View style={[local.tableRow, local.tableHeader]}>
                <Text style={[local.label, local.courseCell]}>코스</Text>
                <Text style={[local.label, local.numberCell]}>온도 °C</Text>
                <Text style={[local.label, local.numberCell]}>탈수 rpm</Text>
              </View>
              {preview.courses.map((course, courseIndex) => (
                <View key={course.id} style={courseIndex > 0 && local.courseDivider}>
                  {course.settings.map(({ temp, spin }, index) => (
                    <View
                      key={`${temp}-${spin}`}
                      accessible
                      accessibilityLabel={`${course.name}, ${temp}도, 분당 ${spin}회 회전`}
                      style={[local.tableRow, index > 0 && local.continuationRow]}
                    >
                      <Text style={[local.tableValue, local.courseCell]}>
                        {index === 0 ? course.name : ''}
                      </Text>
                      <Text style={[local.tableValue, local.numberCell, local.numeric]}>{temp}</Text>
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
        <View style={[styles.actionDock, { marginBottom: 98 + insets.bottom }]}>
          {saveError && <Notice tone="error">세탁기를 저장하지 못했어요. 다시 시도해 주세요.</Notice>}
          <View style={styles.actionDockRow}>
            <View style={local.dockModel}>
              <Text style={local.label}>{isRegistered ? '등록 모델' : '선택한 모델'}</Text>
              <Text style={styles.rowTitle}>{preview.model}</Text>
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
  active: {
    flexDirection: 'row', alignItems: 'center',
  },
  activeDetail: { flex: 1, minWidth: 0, gap: 2 },
  label: { color: palette.muted, fontSize: 12, fontWeight: '700' },
  registeredBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 7, paddingHorizontal: 9,
    backgroundColor: palette.aqua, borderRadius: 13,
  },
  registeredText: { color: palette.accent, fontSize: 12, fontWeight: '700' },
  section: { gap: 12 },
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
  modelDetail: { flex: 1, minWidth: 0, gap: 3 },
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
  dockModel: { gap: 3 },
});
