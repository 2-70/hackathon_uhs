import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View, type ScrollViewInstance } from 'react-native';
import { MachineManual, ManualLink } from '../src/machine-usage';
import type { Garment, Machine } from '../src/model';
import { basketLimit, useLaundry } from '../src/store';
import { checkLoadSetting, machineGuide, planTogether, type TogetherPlan } from '../src/together';
import { Button, Chip, Field, Notice, Screen, palette, styles } from '../src/ui';

const dryerStatus: Record<Garment['dryer'], string> = {
  yes: '건조기 사용 가능',
  no: '건조기 사용 금지',
  unknown: '건조기 사용 여부 확인 필요',
};

export default function Drum() {
  const router = useRouter();
  const { garments, basketIds, removeFromBasket, machine, ready, loadError } = useLaundry();
  const contents = useMemo(() => {
    const wardrobe = new Map(garments.map((garment) => [garment.id, garment]));
    return basketIds.flatMap((id) => wardrobe.get(id) ?? []);
  }, [garments, basketIds]);
  const [unchecked, setUnchecked] = useState<string[]>([]);
  const [completed, setCompleted] = useState<{ garments: Garment[]; plan: TogetherPlan; machine: Machine | null } | null>(null);
  const selection = contents.filter(({ id }) => !unchecked.includes(id));
  const together = completed?.garments.length === selection.length
    && selection.every((item, index) => item === completed.garments[index])
    && completed.machine === machine ? completed.plan : null;
  const scrollRef = useRef<ScrollViewInstance>(null);
  const planTop = useRef(0);
  const openPlanOnLayout = useRef(false);
  const openWardrobe = () => router.push('/wardrobe');
  const openMachines = () => router.replace('/machines');

  function toggleGarment(id: string) {
    setCompleted(null);
    setUnchecked((previous) => previous.includes(id) ? previous.filter((item) => item !== id) : [...previous, id]);
  }

  function startPlan() {
    if (!selection.length) return;
    openPlanOnLayout.current = true;
    setCompleted({ garments: selection, plan: planTogether(selection, machine), machine });
  }

  function renderAction() {
    if (loadError) return null;
    if (!ready) {
      return (
        <View style={drum.loading} accessibilityLiveRegion="polite">
          <ActivityIndicator color={palette.accent} size="small" />
          <Text style={styles.body}>옷장 불러오는 중</Text>
        </View>
      );
    }
    if (!contents.length) return <Button onPress={openWardrobe}>옷장에서 담기</Button>;
    if (together) {
      return (
        <Button onPress={() => scrollRef.current?.scrollTo({ y: planTop.current, animated: true })}>
          세탁 계획 보기
        </Button>
      );
    }
    return <Button disabled={selection.length === 0} onPress={startPlan}>세탁 계획 만들기</Button>;
  }

  return (
    <Screen scrollRef={scrollRef}>
      {loadError && <Notice tone="error">{loadError}</Notice>}

      <View style={[styles.card, styles.cardContent, drum.load]}>
        <LoadReadout count={contents.length} />
        <View style={[styles.card, drum.machineRow]}>
          <View style={styles.iconBadge} importantForAccessibility="no-hide-descendants">
            <Ionicons name="water-outline" size={19} color={palette.accent} />
          </View>
          <View style={drum.itemName}>
            <Text style={styles.rowMeta}>선택한 세탁기</Text>
            <Text style={styles.rowTitle}>{machine ? machine.maker + ' ' + machine.model : '모델 미등록'}</Text>
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
      </View>

      {contents.length > 0 && (
        <View style={[styles.card, drum.collection]}>
          <View style={drum.sectionHeader}>
            <Text accessibilityRole="header" style={[styles.title, drum.itemName]}>세탁할 옷 · {selection.length}벌 선택</Text>
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
              <Pressable
                accessibilityRole="checkbox"
                accessibilityLabel={garment.name}
                accessibilityState={{ checked: !unchecked.includes(garment.id) }}
                onPress={() => toggleGarment(garment.id)}
                style={({ pressed }) => [drum.itemTarget, pressed && styles.dimmed]}
              >
                <Ionicons name={unchecked.includes(garment.id) ? 'square-outline' : 'checkbox'}
                  size={22} color={palette.accent} accessible={false} />
                <View style={[styles.iconBadge, drum.thumbnail]}>
                  {garment.photo || garment.labelPhoto ? (
                    <Image source={{ uri: garment.photo ?? garment.labelPhoto }} style={drum.photo} />
                  ) : <Ionicons name="shirt-outline" size={19} color={palette.accent} />}
                </View>
                <View style={drum.itemName}>
                  <Text style={styles.rowTitle}>{garment.name}</Text>
                  {!!garment.material && <Text style={styles.rowMeta}>{garment.material}</Text>}
                </View>
              </Pressable>
              <Pressable
                style={({ pressed }) => [drum.remove, pressed && styles.dimmed]}
                accessibilityRole="button"
                accessibilityLabel={garment.name + ' 드럼에서 빼기'}
                onPress={() => {
                  setCompleted(null);
                  setUnchecked((previous) => previous.filter((id) => id !== garment.id));
                  removeFromBasket(garment.id);
                }}
              >
                <Ionicons name="close" size={20} color={palette.muted} />
              </Pressable>
            </View>
          ))}
        </View>
      )}

      <View style={drum.action}>{renderAction()}</View>

      {together && (
        <View style={drum.results} onLayout={({ nativeEvent }) => {
          planTop.current = nativeEvent.layout.y;
          if (openPlanOnLayout.current) {
            openPlanOnLayout.current = false;
            requestAnimationFrame(() => scrollRef.current?.scrollTo({ y: planTop.current, animated: false }));
          }
        }}>
          <TogetherDetails plan={together} machine={machine} />
          <DryingDetails garments={selection} />
          {!machine && together.loads.length > 0 && (
            <View style={[styles.card, drum.resultSection]}>
              <Text style={styles.body}>세탁기를 등록하면 그 모델의 코스·온도·탈수 설정까지 골라 드려요.</Text>
              <Button tone="secondary" onPress={openMachines}>세탁기 등록</Button>
            </View>
          )}
          {machine?.catalog && (
            <View style={[styles.card, drum.resultSection]}>
              <Text accessibilityRole="header" style={styles.title}>{machine.model} 설명서</Text>
              <Text style={styles.body}>설명서의 코스와 온도·탈수 설정에서 옷 라벨의 제한을 충족하는 조합을 확인해 주세요.</Text>
              <MachineManual machine={machine} />
            </View>
          )}
        </View>
      )}
    </Screen>
  );
}

function LoadReadout({ count }: { count: number }) {
  return (
    <View
      accessible
      accessibilityLabel={`담은 옷 ${count}벌`}
      accessibilityLiveRegion="polite"
      style={drum.readout}
    >
      <View style={drum.loadCanvas}>
        <View style={drum.loadOuterRing} />
        <View style={drum.loadMiddleRing} />
        <View style={drum.loadCircle}>
          <Ionicons name="shirt-outline" size={20} color={palette.accent} />
          <Text style={drum.count}>{count}<Text style={drum.countUnit}>벌</Text></Text>
          <Text style={styles.rowMeta}>담은 옷</Text>
        </View>
      </View>
    </View>
  );
}
function TogetherDetails({ plan, machine }: { plan: TogetherPlan; machine: Machine | null }) {
  const router = useRouter();
  const list = (items: Garment[]) => items.map(({ name }) => name).join(', ');
  const together = plan.loads.length === 1 && plan.loads[0].garments.length > 1
    && plan.apart.length === 0 && plan.pending.length === 0;
  const summary = together ? '선택한 옷을 한 묶음으로 세탁할 수 있어요.' : [
    plan.loads.length ? `기계세탁 ${plan.loads.length}회` : '기계세탁 대상 없음',
    plan.apart.length ? `별도 관리 ${plan.apart.length}벌` : null,
    plan.pending.length ? `라벨 확인 ${plan.pending.length}벌` : null,
  ].filter(Boolean).join(' · ');
  return (
    <>
      <View style={drum.resultHeading}>
        <Text accessibilityRole="header" style={styles.title}>함께 빨기 계획</Text>
        <Text style={styles.muted}>{summary}</Text>
      </View>
      {(plan.conflicts.length > 0 || plan.apart.length > 0) && (
        <View style={[styles.card, drum.resultSection]}>
          <Text accessibilityRole="header" style={styles.title}>같이 빨면 안 돼요</Text>
          {plan.conflicts.map(({ first, second, reason }) => (
            <View key={`${first[0].id}-${reason}`} style={drum.dryingRow}>
              <Text style={styles.rowTitle}>{list(first)}</Text>
              <Text style={[styles.rowMeta, drum.dryerCaution]}>✕ {list(second)}</Text>
              <Text style={styles.muted}>{reason}</Text>
            </View>
          ))}
          {plan.apart.map(({ garment, reason }) => (
            <View key={garment.id} style={drum.dryingRow}>
              <Text style={styles.rowTitle}>{garment.name}</Text>
              <Text style={styles.muted}>{reason}</Text>
            </View>
          ))}
        </View>
      )}
      {plan.pending.length > 0 && (
        <View style={[styles.card, drum.resultSection]}>
          <Text accessibilityRole="header" style={styles.title}>세탁 전 라벨 확인</Text>
          {plan.pending.map(({ garment, reason }) => (
            <View key={garment.id} style={drum.excludedRow}>
              <View style={drum.itemName}>
                <Text style={styles.rowTitle}>{garment.name}</Text>
                <Text style={styles.muted}>{reason}</Text>
              </View>
              <Pressable accessibilityRole="button" accessibilityLabel={`${garment.name} 정보 수정`}
                onPress={() => router.push({ pathname: '/garment', params: { id: garment.id } })}
                style={({ pressed }) => [drum.link, pressed && styles.dimmed]}>
                <Text style={drum.linkText}>정보 수정</Text>
              </Pressable>
            </View>
          ))}
        </View>
      )}
      {plan.loads.map((load, index) => (
        <View key={load.garments.map(({ id }) => id).join()} style={[styles.card, drum.resultSection]}>
          <Text style={drum.groupMeta}>{plan.loads.length > 1 ? (index + 1) + '회차 · ' : ''}{load.label} · {load.garments.length}벌</Text>
          <Text style={styles.rowTitle}>{list(load.garments)}</Text>
          <Text style={styles.muted}>{load.advice}</Text>
          <MachineSteps garments={load.garments} machine={machine} />
        </View>
      ))}
      {plan.cautions.length > 0 && (
        <View style={[styles.card, drum.resultSection]}>
          <Text accessibilityRole="header" style={styles.title}>함께 빨 때 주의</Text>
          {plan.cautions.map((line) => <Text key={line} style={styles.body}>· {line}</Text>)}
        </View>
      )}
      {plan.notes.length > 0 && (
        <View style={[styles.card, drum.resultSection]}>
          <Text accessibilityRole="header" style={styles.title}>옷별로 챙길 점</Text>
          {plan.notes.map(({ garment, lines }) => (
            <View key={garment.id} style={drum.dryingRow}>
              <Text style={styles.rowTitle}>{garment.name}</Text>
              {lines.map((line) => <Text key={line} style={styles.muted}>{line}</Text>)}
            </View>
          ))}
        </View>
      )}
    </>
  );
}

function MachineSteps({ garments, machine }: { garments: Garment[]; machine: Machine | null }) {
  if (!machine) return null;
  const guide = machineGuide(garments, machine);
  if (!guide) {
    const hasSettings = machine.courses.some((course) => course.verifiedSettings?.length);
    return <Notice>{hasSettings
      ? '이 묶음에 맞는 설정을 확인하지 못했어요. 옷 라벨의 온도·세탁 강도와 모델 설명서를 확인해 주세요.'
      : '이 모델의 확인된 코스·온도·탈수 조합이 아직 없어요. 라벨과 설명서에서 지원 코스와 온도·탈수를 확인한 뒤 설정하세요.'}</Notice>;
  }
  return (
    <View style={drum.validation}>
      <Text style={styles.rowTitle}>{machine.maker} {machine.model} {guide.checks.length ? '확인할 설정' : '설정 방법'}</Text>
      {guide.checks.length > 0 && <Notice>{`이 조합은 조건부예요. 아래 값을 확인하기 전에는 설정을 적용하지 마세요.\n${guide.checks.join('\n')}`}</Notice>}
      {guide.steps.map((line, index) => <Text key={line} style={styles.body}>{index + 1}. {line}</Text>)}
      <ManualLink url={guide.sourceUrl} label="공식 설명서에서 설정 보기" />
      {guide.setting.temperatureCelsius !== null && guide.setting.spinRpm !== null && (
        <Validation key={`${machine.id}-${guide.setting.id}`} garments={garments} machine={machine}
          initialCourse={guide.courseId} initialTemp={guide.setting.temperatureCelsius} initialSpin={guide.setting.spinRpm} />
      )}
    </View>
  );
}

function DryingDetails({ garments }: { garments: Garment[] }) {
  return (
    <View style={[styles.card, drum.resultSection]}>
      <Text accessibilityRole="header" style={styles.title}>건조 안내</Text>
      {garments.map((garment) => (
        <View key={garment.id} style={drum.dryingRow}>
          <Text style={styles.rowTitle}>{garment.name}</Text>
          <Text style={[styles.body, garment.dryer === 'no' && drum.dryerCaution]}>{dryerStatus[garment.dryer]}</Text>
          <Text style={styles.muted}>{garment.drying || '자연건조 방법 확인 필요'}</Text>
        </View>
      ))}
    </View>
  );
}

function Validation({ garments, machine, initialCourse, initialTemp, initialSpin }: {
  garments: Garment[]; machine: Machine; initialCourse: string; initialTemp: number; initialSpin: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [courseId, setCourseId] = useState(initialCourse);
  const [temperature, setTemperature] = useState(String(initialTemp));
  const [spin, setSpin] = useState(String(initialSpin));
  const [result, setResult] = useState<ReturnType<typeof checkLoadSetting> | null>(null);

  function numberFromInput(value: string) {
    return /^\d+$/.test(value.trim()) ? Number(value) : Number.NaN;
  }

  function change(setter: (value: string) => void, value: string) {
    setter(value);
    setResult(null);
  }

  return (
    <View>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }}
        onPress={() => setExpanded((previous) => !previous)}
        style={({ pressed }) => [drum.validationToggle, pressed && styles.dimmed]}>
        <Text style={[drum.linkText, drum.itemName]}>{expanded ? '설정 검증 닫기' : '현재 설정 검증'}</Text>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={palette.accent} />
      </Pressable>
      {expanded && (
        <View style={drum.validationFields}>
          <View style={styles.wrap}>
            {machine.courses.map((course) => (
              <Chip key={course.id} selected={courseId === course.id} onPress={() => change(setCourseId, course.id)}>
                {course.panelName ?? course.name}
              </Chip>
            ))}
            <Chip selected={!courseId} onPress={() => change(setCourseId, '')}>코스 모름</Chip>
          </View>
          <Field label="온도 (℃, 냉수는 0)" value={temperature} onChangeText={(value) => change(setTemperature, value)} keyboardType="number-pad" />
          <Field label="탈수 (rpm, 미사용은 0)" value={spin} onChangeText={(value) => change(setSpin, value)} keyboardType="number-pad" />
          <Button onPress={() => setResult(checkLoadSetting(garments, machine, courseId, numberFromInput(temperature), numberFromInput(spin)))}>
            설정 확인
          </Button>
          {result && (
            <Notice tone={result.status === 'ok' ? 'success' : result.status === 'adjust' ? 'error' : 'info'}>
              {({ ok: '적합', adjust: '수정 필요', unknown: '판단 불가' })[result.status]}
              {'\n' + result.reasons.join('\n')}
            </Notice>
          )}
        </View>
      )}
    </View>
  );
}

const drum = StyleSheet.create({
  load: { gap: 13, padding: 15 },
  readout: { padding: 9, borderRadius: 20, backgroundColor: palette.accentWash, alignItems: 'center' },
  loadCanvas: { width: 158, height: 158, alignItems: 'center', justifyContent: 'center' },
  loadOuterRing: { position: 'absolute', width: 154, height: 154, borderRadius: 77, backgroundColor: palette.lilac, borderWidth: 1, borderColor: palette.violet, opacity: 0.55 },
  loadMiddleRing: { position: 'absolute', width: 136, height: 136, borderRadius: 68, backgroundColor: palette.violet, opacity: 0.42 },
  loadCircle: { width: 122, height: 122, alignSelf: 'center', borderRadius: 61, borderWidth: 5, borderColor: palette.surface, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.surface },
  count: { color: palette.ink, fontSize: 37, lineHeight: 42, fontWeight: '800', letterSpacing: -1.2, fontVariant: ['tabular-nums'] },
  countUnit: { color: palette.muted, fontSize: 16, letterSpacing: 0 },
  machineRow: { flexDirection: 'row', alignItems: 'center', gap: 9, minHeight: 58, paddingVertical: 6, paddingHorizontal: 10, backgroundColor: palette.paper },
  action: { width: '100%', maxWidth: 270, alignSelf: 'center' },
  link: { minHeight: 44, paddingHorizontal: 5, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 3 },
  linkText: { color: palette.accent, fontSize: 13, lineHeight: 19, fontWeight: '700' },
  loading: { minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, paddingHorizontal: 9, borderRadius: 13, backgroundColor: palette.accentWash },
  collection: { paddingHorizontal: 13, paddingTop: 3, paddingBottom: 4 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44, paddingVertical: 3 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 7, borderTopWidth: 1, borderTopColor: palette.line },
  itemTarget: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 },
  itemName: { flex: 1, minWidth: 0 },
  thumbnail: { overflow: 'hidden' },
  photo: { width: '100%', height: '100%' },
  remove: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  results: { gap: 11 },
  resultHeading: { paddingVertical: 4, gap: 4 },
  groupMeta: { color: palette.accent, fontSize: 12, lineHeight: 17, fontWeight: '700', fontVariant: ['tabular-nums'] },
  validationToggle: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  validation: { gap: 11, padding: 12, marginBottom: 8, borderRadius: 12, backgroundColor: palette.subtle },
  validationFields: { gap: 10 },
  resultSection: { padding: 13, gap: 10 },
  excludedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 9, borderTopWidth: 1, borderTopColor: palette.line },
  dryingRow: { paddingTop: 9, gap: 2, borderTopWidth: 1, borderTopColor: palette.line },
  dryerCaution: { color: palette.error },
});
