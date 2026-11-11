import Ionicons from '@expo/vector-icons/Ionicons';
import * as ImagePicker from 'expo-image-picker';
import { useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Image, Platform, Pressable, StyleSheet, Text, View, type ScrollViewInstance } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { identifyMachine, readMachineChoice, searchMachines } from '../src/api';
import { MachineManual, ManualLink } from '../src/machine-usage';
import type { Machine, MachineChoice } from '../src/model';
import { useLaundry } from '../src/store';
import { Button, Notice, Screen, SearchField, palette, styles } from '../src/ui';

type SearchResult = { query: string; page: number; attempt: number } & (
  | { status: 'error' }
  | { status: 'ready'; data: Awaited<ReturnType<typeof searchMachines>> }
);
type DetailResult = { choice: MachineChoice; attempt: number; machine: Machine | null };
type PhotoResult = Awaited<ReturnType<typeof identifyMachine>>;

// What the app can do for a model, in the user's words rather than catalog terms.
function describeModel({ maker, catalog }: MachineChoice) {
  if (!catalog) return `${maker} · 코스·온도 추천 가능`;
  return [
    maker, catalog.capacityKg === null ? null : `세탁 용량 ${catalog.capacityKg}kg`,
    catalog.hasManual ? '설명서 보기 가능' : '설명서 없음',
  ].filter(Boolean).join(' · ');
}

function ModelRow({ candidate, checked, registered, divided, disabled, onPress }: {
  candidate: MachineChoice; checked: boolean; registered: boolean; divided: boolean; disabled: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        local.result, divided && local.resultDivider, checked && local.selected, pressed && styles.dimmed,
      ]}
    >
      <View style={[local.radio, checked && local.radioChecked]}>
        {checked && <View style={local.radioDot} />}
      </View>
      <View style={local.modelDetail}>
        <Text style={styles.rowTitle}>{candidate.model}</Text>
        <Text style={styles.rowMeta}>{describeModel(candidate)}</Text>
      </View>
      {registered && (
        <View style={local.inUseBadge}>
          <Text style={local.inUse}>등록됨</Text>
        </View>
      )}
    </Pressable>
  );
}

export default function MachinesScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { machine, ready, loadError, registerMachine } = useLaundry();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [searchAttempt, setSearchAttempt] = useState(0);
  const [selected, setSelected] = useState<MachineChoice | null>(null);
  const [detail, setDetail] = useState<DetailResult | null>(null);
  const [detailAttempt, setDetailAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const scroll = useRef<ScrollViewInstance>(null);
  const scrollToDetail = useRef(false);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoResult, setPhotoResult] = useState<PhotoResult | null>(null);
  const [photoError, setPhotoError] = useState('');
  // The model list opens when a photo does not settle the model, or when the user asks for it.
  const [showList, setShowList] = useState(false);

  useEffect(() => {
    if (!showList) return;
    let active = true;
    const timer = setTimeout(() => {
      void searchMachines(query, page).then(
        (data) => { if (active) setResult({ query, page, attempt: searchAttempt, status: 'ready', data }); },
        () => { if (active) setResult({ query, page, attempt: searchAttempt, status: 'error' }); },
      );
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [query, page, searchAttempt, showList]);

  useEffect(() => {
    if (!selected || selected.id === machine?.id) return;
    let active = true;
    void readMachineChoice(selected).then(
      (value) => { if (active) setDetail({ choice: selected, attempt: detailAttempt, machine: value }); },
      () => { if (active) setDetail({ choice: selected, attempt: detailAttempt, machine: null }); },
    );
    return () => { active = false; };
  }, [selected, machine, detailAttempt]);

  const search = result?.query === query && result.page === page && result.attempt === searchAttempt ? result : null;
  const matches = search?.status === 'ready' ? search.data : null;
  const selection = selected ?? machine;
  const isRegistered = selection !== null && selection.id === machine?.id;
  const currentDetail = detail?.choice === selected && detail?.attempt === detailAttempt ? detail : null;
  const preview = isRegistered ? machine : currentDetail?.machine ?? null;

  function changeQuery(value: string) {
    setQuery(value);
    setPage(1);
  }

  function choose(candidate: MachineChoice) {
    if (candidate.id !== selection?.id) scrollToDetail.current = true;
    setSelected(candidate);
    setSaveError(false);
  }

  async function findByPhoto(fromCamera: boolean) {
    if (photoBusy || saving) return;
    setPhotoError('');
    try {
      if (fromCamera && Platform.OS !== 'web') {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setPhotoError('카메라 권한이 없어요. 사진을 선택하거나 목록에서 골라 주세요.');
          setShowList(true);
          return;
        }
      }
      const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.9 };
      const picked = fromCamera
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
      if (picked.canceled) return;
      const asset = picked.assets[0];
      setPhotoUri(asset.uri);
      setPhotoResult(null);
      setPhotoBusy(true);
      const found = await identifyMachine(asset, Platform.OS === 'web');
      setPhotoResult(found);
      if (found.status === 'not_found') {
        setShowList(true);
      } else if (found.status === 'matched') {
        // Exactly one model carries the printed name, so register it without another step.
        const [match] = found.machines;
        setSelected(match);
        if (match.id !== machine?.id) await save(await readMachineChoice(match));
      }
    } catch (error) {
      setPhotoError(error instanceof Error && error.message ? error.message : '사진으로 모델을 찾지 못했어요.');
      setShowList(true);
    } finally {
      setPhotoBusy(false);
    }
  }

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
      <Screen scrollRef={scroll}>
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
          <Text accessibilityRole="header" style={styles.title}>사진으로 등록</Text>
          <Text style={styles.muted}>
            모델명이 적힌 스티커를 찍어 주세요. 보통 세탁기 문 안쪽 테두리나 옆면·뒷면에 붙어 있어요.
          </Text>
          {photoUri && (
            <View style={local.photoRow}>
              <Image accessibilityLabel="세탁기 사진" source={{ uri: photoUri }} style={local.photo} />
              <Text style={[styles.rowMeta, local.modelDetail]}>
                {photoBusy ? '사진에서 모델명을 읽는 중이에요…' : '사진 확인 완료'}
              </Text>
            </View>
          )}
          <View style={local.photoActions}>
            <View style={local.modelDetail}>
              <Button icon="camera-outline" disabled={photoBusy || saving} onPress={() => void findByPhoto(true)}>
                {photoUri ? '다시 촬영' : '촬영'}
              </Button>
            </View>
            <View style={local.modelDetail}>
              <Button tone="secondary" icon="images-outline" disabled={photoBusy || saving}
                onPress={() => void findByPhoto(false)}>
                사진 선택
              </Button>
            </View>
          </View>
          {photoError !== '' && <Notice tone="error">{photoError}</Notice>}
          {photoResult && !photoBusy && (photoResult.status === 'matched' ? (
            <Notice tone="success">
              {photoResult.machines[0].id === machine?.id
                ? `${photoResult.machines[0].model} 모델을 찾아 내 세탁기로 등록했어요.`
                : photoResult.message}
            </Notice>
          ) : <Notice>{photoResult.message}</Notice>)}
          {photoResult?.status === 'candidates' && !photoBusy && (
            <View accessibilityRole="radiogroup">
              {photoResult.machines.map((candidate, index) => (
                <ModelRow key={candidate.id} candidate={candidate} checked={candidate.id === selection?.id}
                  registered={candidate.id === machine?.id} divided={index > 0} disabled={saving}
                  onPress={() => choose(candidate)} />
              ))}
            </View>
          )}
          <Text style={local.label}>모델명을 읽기 위해 사진을 WashWise 서버로 보내요.</Text>
          {!showList && (
            <Button tone="quiet" icon="list-outline" onPress={() => setShowList(true)}>목록에서 직접 찾기</Button>
          )}
        </View>

        {showList && (
        <View style={[styles.card, styles.cardContent, local.section]}>
          <Text accessibilityRole="header" style={styles.title}>목록에서 직접 찾기</Text>
          <SearchField
            label="제조사 또는 모델명"
            value={query}
            onChangeText={changeQuery}
            placeholder="제조사 또는 모델명"
            autoCapitalize="none"
            autoCorrect={false}
          />

          {search === null ? (
            <Notice>모델을 찾는 중이에요.</Notice>
          ) : search.status === 'error' ? (
            <View style={local.feedback}>
              <Notice tone="error">모델 목록을 불러오지 못했어요.</Notice>
              <Button tone="secondary" onPress={() => setSearchAttempt((attempt) => attempt + 1)}>다시 검색</Button>
            </View>
          ) : matches?.machines.length === 0 && !matches.partial ? (
            <View style={local.feedback}>
              <Text style={styles.title}>일치하는 세탁기 모델이 없어요</Text>
              <Text style={styles.muted}>모델명의 일부만 입력해 보세요.</Text>
              {query.length > 0 && <Button tone="secondary" onPress={() => changeQuery('')}>검색어 지우기</Button>}
            </View>
          ) : matches && (
            <View accessibilityRole="radiogroup">
              <View style={local.listHeader}>
                {matches.catalogTotal !== null && <Text style={local.label}>국내 등록 세탁기 {matches.catalogTotal.toLocaleString('ko-KR')}개</Text>}
                {matches.partial && (
                  <View style={local.feedback}>
                    <Notice tone="error">일부 모델을 불러오지 못했어요.</Notice>
                    <Button tone="secondary" onPress={() => setSearchAttempt((attempt) => attempt + 1)}>다시 검색</Button>
                  </View>
                )}
              </View>
              {matches.machines.map((candidate, index) => (
                <ModelRow key={candidate.id} candidate={candidate} checked={candidate.id === selection?.id}
                  registered={candidate.id === machine?.id} divided={index > 0} disabled={saving}
                  onPress={() => choose(candidate)} />
              ))}
              {matches.totalPages > 1 && (
                <View style={local.pagination}>
                  <Button tone="secondary" disabled={page <= 1} onPress={() => setPage(page - 1)}>이전</Button>
                  <Text style={local.label}>{page} / {matches.totalPages}</Text>
                  <Button tone="secondary" disabled={page >= matches.totalPages} onPress={() => setPage(page + 1)}>다음</Button>
                </View>
              )}
            </View>
          )}
        </View>
        )}

        {selection && (
          <View key={selection.id} style={[styles.card, styles.cardContent, local.section]}
            onLayout={({ nativeEvent }) => {
              if (!scrollToDetail.current) return;
              scrollToDetail.current = false;
              scroll.current?.scrollTo({ y: nativeEvent.layout.y, animated: true });
            }}>
            <View style={local.tableTitle}>
              <Text accessibilityRole="header" style={styles.title}>모델 사용법</Text>
              <Text style={local.label}>{selection.model}</Text>
            </View>
            {!preview && (currentDetail ? (
              <View style={local.feedback}>
                <Notice tone="error">모델 사용법을 불러오지 못했어요.</Notice>
                <Button tone="secondary" onPress={() => setDetailAttempt((attempt) => attempt + 1)}>다시 불러오기</Button>
              </View>
            ) : <Notice>모델 사용법을 불러오는 중이에요.</Notice>)}
            {preview && (preview.courses.some((course) => course.verifiedSettings?.length) ? (
              <View style={local.table}>
              <View style={[local.tableRow, local.tableHeader]}>
                <Text style={[local.label, local.courseCell]}>코스</Text>
                <Text style={[local.label, local.numberCell]}>물온도</Text>
                <Text style={[local.label, local.numberCell]}>탈수</Text>
              </View>
              {preview.courses.filter((course) => course.verifiedSettings?.length).map((course, courseIndex) => (
                <View key={course.id} style={courseIndex > 0 && local.courseDivider}>
                  {(course.verifiedSettings ?? []).map(({ id, temperature, spin, isDefault, waterLevel, dryLevel, sourceUrl, manualPage }, index) => (
                    <View key={id} style={index > 0 && local.continuationRow}>
                    <View
                      accessible
                      accessibilityLabel={`${course.name}, 물온도 ${temperature}, 탈수 ${spin}`}
                      style={local.tableRow}
                    >
                      <Text style={[local.tableValue, local.courseCell]}>
                        {index === 0 ? (course.panelName ?? course.name) : ''}{isDefault ? ' · 기본' : ''}
                      </Text>
                      <Text style={[local.tableValue, local.numberCell, local.numeric]}>{temperature}</Text>
                      <Text style={[local.tableValue, local.numberCell, local.numeric]}>{spin}</Text>
                    </View>
                    <View style={local.settingDetails}>
                      {waterLevel && <Text style={styles.rowMeta}>물 높이 {waterLevel}</Text>}
                      {dryLevel && <Text style={styles.rowMeta}>건조 {dryLevel}</Text>}
                      <ManualLink url={sourceUrl} label={manualPage ? `설명서 ${manualPage}쪽` : '설정 출처'} />
                    </View>
                    </View>
                  ))}
                </View>
              ))}
              </View>
            ) : <Notice>이 모델의 코스별 온도·탈수 조합은 아직 확인되지 않았어요.</Notice>)}
            {preview && <MachineManual machine={preview} />}
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
  photoRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  photo: { width: 64, height: 64, borderRadius: 12, backgroundColor: palette.subtle },
  photoActions: { flexDirection: 'row', gap: 8 },
  feedback: { alignItems: 'flex-start', gap: 8, paddingVertical: 8 },
  listHeader: { paddingVertical: 7, paddingHorizontal: 3 },
  pagination: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 10 },
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
  settingDetails: { flexDirection: 'row', flexWrap: 'wrap', gap: 9, paddingHorizontal: 9, paddingBottom: 9 },
  courseCell: { flex: 1.3 },
  numberCell: { flex: 0.8, textAlign: 'right' },
  tableValue: { color: palette.ink, fontSize: 14, fontWeight: '600' },
  numeric: { fontVariant: ['tabular-nums'] },
  dockModel: { gap: 3 },
});
