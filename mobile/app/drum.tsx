import Ionicons from '@expo/vector-icons/Ionicons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View, type ScrollViewInstance } from 'react-native';
import { calculatePlan, validateSettings } from '../src/mock';
import type { Garment, Machine, Plan } from '../src/model';
import { basketLimit, useLaundry } from '../src/store';
import { Button, Chip, Field, Notice, ProgressRing, Screen, palette, styles } from '../src/ui';

type PlanInput = { garments: Garment[]; machine: Machine };
type PlanRequest = {
  input: PlanInput;
  attempt: number;
  outcome: { plan: Plan } | { error: string };
};

const dryerStatus: Record<Garment['dryer'], string> = {
  yes: '건조기 사용 가능',
  no: '건조기 사용 금지',
  unknown: '건조기 사용 여부 확인 필요',
};

export default function Drum() {
  const router = useRouter();
  const { focus } = useLocalSearchParams<{ focus?: string }>();
  const {
    garments, basketIds, removeFromBasket, machine, ready, loadError, analysisStarted, startAnalysis,
  } = useLaundry();
  const contents = useMemo(() => {
    const selected = new Set(basketIds);
    return garments.filter(({ id }) => selected.has(id));
  }, [garments, basketIds]);
  const hasNumericSettings = machine?.courses.some((course) => course.settings.length > 0) ?? false;
  const input = useMemo(() => (
    analysisStarted && machine && hasNumericSettings && contents.length > 0
      ? { garments: contents, machine } : null
  ), [analysisStarted, machine, hasNumericSettings, contents]);
  const [attempt, setAttempt] = useState(0);
  const [completed, setCompleted] = useState<PlanRequest | null>(null);
  const scrollRef = useRef<ScrollViewInstance>(null);
  const planTop = useRef(0);
  const openPlanOnLayout = useRef(focus === 'plan');

  useEffect(() => {
    if (!input) return;
    let active = true;
    void calculatePlan(input.garments, input.machine).then(
      (plan) => { if (active) setCompleted({ input, attempt, outcome: { plan } }); },
      () => {
        if (active) setCompleted({
          input, attempt, outcome: { error: '세탁 계획을 불러오지 못했습니다. 다시 시도해 주세요.' },
        });
      },
    );
    return () => { active = false; };
  }, [input, attempt]);

  // The current input also gates display before effect cleanup has run.
  const outcome = completed?.input === input && completed.attempt === attempt ? completed.outcome : null;
  const plan = outcome && 'plan' in outcome ? outcome.plan : null;
  const error = outcome && 'error' in outcome ? outcome.error : null;
  const busy = !!input && !outcome;
  const openWardrobe = () => router.push('/wardrobe');
  const openMachines = () => router.push('/machines');

  function renderAction() {
    if (loadError) return null;
    if (!ready || busy) {
      return (
        <View style={drum.loading} accessibilityLiveRegion="polite">
          <ActivityIndicator color={palette.accent} size="small" />
          <Text style={styles.body}>{ready ? '세탁 계획 계산 중' : '옷장 불러오는 중'}</Text>
        </View>
      );
    }
    if (error) return <Button onPress={() => setAttempt((previous) => previous + 1)}>다시 계산</Button>;
    if (plan) {
      return (
        <Button onPress={() => scrollRef.current?.scrollTo({ y: planTop.current, animated: true })}>
          세탁 계획 보기
        </Button>
      );
    }
    if (!contents.length) return <Button onPress={openWardrobe}>옷장에서 담기</Button>;
    if (!machine) return <Button onPress={openMachines}>세탁기 등록</Button>;
    if (!hasNumericSettings) return <Notice>공식 설명서에서 온도와 탈수의 수치 조합을 확인하지 못해 이 모델의 세탁 계획은 계산할 수 없어요.</Notice>;
    return <Button onPress={startAnalysis}>세탁 분석 시작</Button>;
  }

  return (
    <Screen scrollRef={scrollRef}>
      <Text accessibilityRole="header" style={drum.heading}>가상 드럼</Text>
      {loadError && <Notice tone="error">{loadError}</Notice>}

      <View style={drum.load}>
        <LoadReadout count={contents.length} />
        <View style={drum.machineRow}>
          <View style={drum.machineIcon} importantForAccessibility="no-hide-descendants">
            <Ionicons name="options-outline" size={19} color={palette.accent} />
          </View>
          <View style={drum.itemName}>
            <Text style={drum.label}>세탁기</Text>
            <Text style={drum.rowTitle}>{machine ? machine.maker + ' ' + machine.model : '미등록'}</Text>
          </View>
          {(machine || contents.length === 0) && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={machine ? '세탁기 변경' : '세탁기 등록'}
              onPress={openMachines}
              style={({ pressed }) => [drum.link, pressed && styles.dimmed]}
            >
              <Text style={drum.linkText}>{machine ? '변경' : '등록'}</Text>
              <Ionicons name="chevron-forward" size={14} color={palette.accent} />
            </Pressable>
          )}
        </View>
        {error && <Notice tone="error">{error}</Notice>}
        <View style={drum.action}>{renderAction()}</View>
      </View>

      {contents.length > 0 && (
        <View style={drum.collection}>
          <View style={drum.sectionHeader}>
            <Text accessibilityRole="header" style={[styles.title, drum.itemName]}>담은 옷</Text>
            {contents.length < basketLimit && (
              <Pressable
                accessibilityRole="button"
                onPress={openWardrobe}
                style={({ pressed }) => [drum.link, pressed && styles.dimmed]}
              >
                <Ionicons name="add" size={17} color={palette.accent} />
                <Text style={drum.linkText}>옷 추가</Text>
              </Pressable>
            )}
          </View>
          {contents.map((garment) => (
            <View key={garment.id} style={drum.item}>
              <View style={drum.thumbnail}>
                {garment.photo ? <Image source={{ uri: garment.photo }} style={drum.photo} /> : (
                  <Ionicons name="shirt-outline" size={19} color={palette.accent} />
                )}
              </View>
              <View style={drum.itemName}>
                <Text style={drum.rowTitle}>{garment.name}</Text>
                {!!garment.material && <Text style={drum.label}>{garment.material}</Text>}
              </View>
              <Pressable
                style={({ pressed }) => [drum.remove, pressed && styles.dimmed]}
                accessibilityRole="button"
                accessibilityLabel={garment.name + ' 드럼에서 빼기'}
                onPress={() => removeFromBasket(garment.id)}
              >
                <Ionicons name="close" size={20} color={palette.muted} />
              </Pressable>
            </View>
          ))}
        </View>
      )}

      {plan && input && (
        <View onLayout={({ nativeEvent }) => {
          planTop.current = nativeEvent.layout.y;
          if (openPlanOnLayout.current) {
            openPlanOnLayout.current = false;
            requestAnimationFrame(() => scrollRef.current?.scrollTo({ y: planTop.current, animated: false }));
          }
        }}>
          <PlanDetails plan={plan} machine={input.machine} garments={input.garments} />
        </View>
      )}
    </Screen>
  );
}

function LoadReadout({ count }: { count: number }) {
  const remaining = Math.max(0, basketLimit - count);

  return (
    <View
      accessible
      accessibilityLabel={'드럼에 담은 옷 ' + count + '벌, 최대 ' + basketLimit + '벌'}
      accessibilityLiveRegion="polite"
      style={drum.readout}
    >
      <ProgressRing value={count} max={basketLimit} size={156} thickness={10} color={palette.accent} track={palette.surface}>
        <View style={drum.ringLabel}>
          <Text style={drum.count}>{count}<Text style={drum.countUnit}>벌</Text></Text>
          <Text style={drum.label}>담은 옷</Text>
        </View>
      </ProgressRing>
      <View style={drum.loadMetrics}>
        <View style={drum.loadMetric}>
          <Text style={drum.metricValue}>{remaining}벌</Text>
          <Text style={drum.label}>더 담을 수 있는 옷</Text>
        </View>
        <View style={drum.metricDivider} />
        <View style={drum.loadMetric}>
          <Text style={drum.metricValue}>{basketLimit}벌</Text>
          <Text style={drum.label}>드럼 한도</Text>
        </View>
      </View>
    </View>
  );
}

function PlanDetails({ plan, machine, garments }: { plan: Plan; machine: Machine; garments: Garment[] }) {
  const router = useRouter();
  const [validationGroup, setValidationGroup] = useState<string | null>(null);

  return (
    <View style={drum.results}>
      <View style={drum.resultHeading}>
        <Text accessibilityRole="header" style={styles.title}>세탁 계획 · {plan.groups.length}회</Text>
        <Text style={styles.muted}>확인된 코스 및 관리정보 기준 · 적재 용량 미검증</Text>
      </View>
      {plan.groups.map((group, index) => {
        const expanded = validationGroup === group.id;
        const settings = [
          { label: '코스', value: group.course.name },
          { label: '온도', value: group.temp === 0 ? '냉수' : group.temp + ' ℃' },
          { label: '탈수', value: group.spin === 0 ? '사용 안 함' : group.spin + ' rpm' },
        ];
        return (
          <View key={group.id} style={drum.group}>
            <Text style={drum.groupMeta}>{index + 1}회차 · {group.garments.length}벌 · {group.course.gentle ? '약한 세탁' : '일반 세탁'}</Text>
            <Text style={drum.rowTitle}>{group.garments.map(({ name }) => name).join(', ')}</Text>
            <View style={drum.settings}>
              {settings.map(({ label, value }, cellIndex) => (
                <View key={label} style={[drum.setting, cellIndex > 0 && drum.settingDivider]}>
                  <Text style={drum.label}>{label}</Text>
                  <Text style={drum.settingValue}>{value}</Text>
                </View>
              ))}
            </View>
            <Text style={styles.muted}>{group.reason}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded }}
              onPress={() => setValidationGroup((current) => current === group.id ? null : group.id)}
              style={({ pressed }) => [drum.validationToggle, pressed && styles.dimmed]}
            >
              <Text style={[drum.linkText, drum.itemName]}>{expanded ? '설정 검증 닫기' : '현재 설정 검증'}</Text>
              <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={palette.accent} />
            </Pressable>
            {expanded && <Validation key={group.id} group={group} machine={machine} />}
          </View>
        );
      })}
      {plan.excluded.length > 0 && (
        <View style={drum.resultSection}>
          <Text accessibilityRole="header" style={styles.title}>별도 관리 · {plan.excluded.length}벌</Text>
          {plan.excluded.map(({ garment, reason }) => (
            <View key={garment.id} style={drum.excludedRow}>
              <View style={drum.itemName}>
                <Text style={drum.rowTitle}>{garment.name}</Text>
                <Text style={styles.muted}>{reason}</Text>
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={garment.name + ' 정보 수정'}
                onPress={() => router.push({ pathname: '/garment', params: { id: garment.id } })}
                style={({ pressed }) => [drum.link, pressed && styles.dimmed]}
              >
                <Text style={drum.linkText}>정보 수정</Text>
              </Pressable>
            </View>
          ))}
        </View>
      )}
      <View style={drum.resultSection}>
        <Text accessibilityRole="header" style={styles.title}>건조 안내</Text>
        {garments.map((garment) => (
          <View key={garment.id} style={drum.dryingRow}>
            <Text style={drum.rowTitle}>{garment.name}</Text>
            <Text style={[styles.body, garment.dryer === 'no' && drum.dryerCaution]}>{dryerStatus[garment.dryer]}</Text>
            <Text style={styles.muted}>{garment.drying || '자연건조 방법 확인 필요'}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function Validation({ group, machine }: { group: Plan['groups'][number]; machine: Machine }) {
  const [courseId, setCourseId] = useState(group.course.id);
  const [temperature, setTemperature] = useState(String(group.temp));
  const [spin, setSpin] = useState(String(group.spin));
  const [result, setResult] = useState<Awaited<ReturnType<typeof validateSettings>> | null>(null);
  const [busy, setBusy] = useState(false);
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);

  function numberFromInput(value: string) {
    return /^\d+$/.test(value.trim()) ? Number(value) : Number.NaN;
  }

  function change(setter: (value: string) => void, value: string) {
    request.current++;
    setter(value);
    setBusy(false);
    setResult(null);
  }

  async function check() {
    const id = ++request.current;
    setBusy(true);
    setResult(null);
    try {
      const checked = await validateSettings(group, machine, courseId, numberFromInput(temperature), numberFromInput(spin));
      if (id === request.current) setResult(checked);
    } catch {
      if (id === request.current) setResult({ status: 'unknown', reasons: ['설정을 확인하지 못했습니다. 다시 시도해 주세요.'] });
    } finally {
      if (id === request.current) setBusy(false);
    }
  }

  return (
    <View style={drum.validation}>
      <Text style={drum.rowTitle}>실제 세탁기에서 고른 설정</Text>
      <View style={styles.wrap}>
        {machine.courses.map((course) => (
          <Chip key={course.id} selected={courseId === course.id} onPress={() => change(setCourseId, course.id)}>
            {course.name}
          </Chip>
        ))}
        <Chip selected={!courseId} onPress={() => change(setCourseId, '')}>코스 모름</Chip>
      </View>
      <Field label="온도 (℃, 냉수는 0)" value={temperature} onChangeText={(value) => change(setTemperature, value)} keyboardType="number-pad" />
      <Field label="탈수 (rpm, 미사용은 0)" value={spin} onChangeText={(value) => change(setSpin, value)} keyboardType="number-pad" />
      <Button disabled={busy} onPress={() => void check()}>{busy ? '검증 중' : '설정 확인'}</Button>
      {result && (
        <Notice tone={result.status === 'ok' ? 'success' : result.status === 'adjust' ? 'error' : 'info'}>
          {({ ok: '적합', adjust: '수정 필요', unknown: '판단 불가' })[result.status]}
          {'\n' + result.reasons.join('\n')}
        </Notice>
      )}
    </View>
  );
}

const drum = StyleSheet.create({
  heading: { color: palette.ink, textAlign: 'center', fontSize: 20, lineHeight: 28, fontWeight: '800' },
  load: { gap: 13, padding: 15, borderRadius: 18, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface },
  readout: { alignItems: 'center', gap: 14, paddingHorizontal: 12, paddingTop: 14, paddingBottom: 8, borderRadius: 18, backgroundColor: palette.lilac },
  ringLabel: { alignItems: 'center', gap: 1 },
  count: { color: palette.ink, fontSize: 44, lineHeight: 52, fontWeight: '800', letterSpacing: -1.5, fontVariant: ['tabular-nums'] },
  countUnit: { color: palette.muted, fontSize: 16, letterSpacing: 0 },
  loadMetrics: { width: '100%', flexDirection: 'row', alignItems: 'center', paddingTop: 11, paddingBottom: 3, borderTopWidth: 1, borderTopColor: palette.line },
  loadMetric: { flex: 1, alignItems: 'center', gap: 3 },
  metricValue: { color: palette.accent, fontSize: 18, lineHeight: 24, fontWeight: '800', fontVariant: ['tabular-nums'] },
  metricDivider: { width: 1, height: 29, backgroundColor: palette.line },
  machineRow: { flexDirection: 'row', alignItems: 'center', gap: 9, minHeight: 58, paddingVertical: 6, paddingHorizontal: 10, borderWidth: 1, borderColor: palette.line, borderRadius: 13, backgroundColor: palette.paper },
  machineIcon: { width: 35, height: 35, justifyContent: 'center', alignItems: 'center', borderRadius: 12, backgroundColor: palette.accentWash },
  action: { width: '100%', maxWidth: 270, alignSelf: 'center' },
  label: { color: palette.muted, fontSize: 12, lineHeight: 17, fontWeight: '600' },
  link: { minHeight: 44, paddingHorizontal: 5, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 3 },
  linkText: { color: palette.accent, fontSize: 13, lineHeight: 19, fontWeight: '700' },
  loading: { minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, paddingHorizontal: 9, borderRadius: 13, backgroundColor: palette.accentWash },
  collection: { paddingHorizontal: 13, paddingTop: 3, paddingBottom: 4, borderRadius: 16, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44, paddingVertical: 3 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 7, borderTopWidth: 1, borderTopColor: palette.line },
  itemName: { flex: 1, minWidth: 0 },
  thumbnail: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.accentWash, borderRadius: 12, overflow: 'hidden' },
  rowTitle: { color: palette.ink, fontSize: 15, lineHeight: 22, fontWeight: '700' },
  photo: { width: '100%', height: '100%' },
  remove: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  results: { gap: 11 },
  resultHeading: { paddingVertical: 4, gap: 4 },
  group: { gap: 8, paddingHorizontal: 13, paddingTop: 13, paddingBottom: 4, borderRadius: 16, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface },
  groupMeta: { color: palette.accent, fontSize: 12, lineHeight: 17, fontWeight: '700', fontVariant: ['tabular-nums'] },
  settings: { flexDirection: 'row', borderRadius: 12, backgroundColor: palette.subtle },
  setting: { flex: 1, minWidth: 0, paddingHorizontal: 9, paddingVertical: 9, gap: 3 },
  settingDivider: { borderLeftWidth: 1, borderLeftColor: palette.line },
  settingValue: { color: palette.ink, fontSize: 16, lineHeight: 21, fontWeight: '800', fontVariant: ['tabular-nums'] },
  validationToggle: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  validation: { gap: 11, padding: 12, marginBottom: 8, borderRadius: 12, backgroundColor: palette.subtle },
  resultSection: { padding: 13, gap: 10, borderRadius: 16, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface },
  excludedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 9, borderTopWidth: 1, borderTopColor: palette.line },
  dryingRow: { paddingTop: 9, gap: 2, borderTopWidth: 1, borderTopColor: palette.line },
  dryerCaution: { color: palette.error },
});
