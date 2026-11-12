import Ionicons from '@expo/vector-icons/Ionicons';
import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Image, Linking, Platform, Pressable, StyleSheet, Text, useWindowDimensions, View, type TextInputInstance } from 'react-native';

import { analyzePhoto, careSummary, messageWithoutFollowUp, parseMaterialGuidance, splitGuidance, type Analysis, type PhotoKind, type UploadPhoto } from '../src/analysis';
import { blankGarment } from '../src/mock';
import type { Garment, GarmentDraft, GarmentPhotos } from '../src/model';
import { LaundryLoading } from '../src/LaundryLoading';
import { MachineGuideBody } from '../src/machine-usage';
import { basketLimit, useLaundry } from '../src/store';
import { machineGuide } from '../src/together';
import { Button, Field, Notice, Screen, ScreenHeader, palette, styles } from '../src/ui';

type EntryMode = PhotoKind | 'details';
type InvalidField = 'name' | 'temperature';

const entryModes = [
  { id: 'clothing', title: '옷 사진', icon: 'shirt-outline' },
  { id: 'label', title: '세탁 라벨', icon: 'pricetag-outline' },
  { id: 'details', title: '직접 입력', icon: 'create-outline' },
] as const;

const photoCopy = {
  clothing: {
    title: '옷 사진',
    icon: 'shirt-outline',
    guide: '옷 전체가 보이게 찍어요.',
  },
  label: {
    title: '세탁 라벨',
    icon: 'pricetag-outline',
    guide: '세탁 표시를 선명하게 찍어요.',
  },
} as const;

const careSources: Record<GarmentDraft['source'], string> = {
  manual: '직접 입력',
  'sample-label': '세탁 라벨 샘플',
  'sample-product': '상품 관리정보 샘플',
  'care-label': '실물 세탁 라벨',
  'official-product': '상품 관리 정보',
};

const photoOptions: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.9, base64: true };
const washOptions: { value: GarmentDraft['wash']; label: string }[] = [
  { value: 'machine', label: '기계 세탁' },
  { value: 'hand', label: '손세탁' },
  { value: 'none', label: '물세탁 금지' },
  { value: 'unknown', label: '확인 필요' },
];
const dryerOptions: { value: GarmentDraft['dryer']; label: string }[] = [
  { value: 'yes', label: '사용 가능' },
  { value: 'no', label: '사용 금지' },
  { value: 'unknown', label: '확인 필요' },
];
const cycleOptions: { value: NonNullable<GarmentDraft['washStrength']> | 'unknown'; label: string }[] = [
  { value: 'gentle', label: '약한 세탁' },
  { value: 'very_gentle', label: '매우 약한 세탁' },
  { value: 'normal', label: '일반 세탁' },
  { value: 'unknown', label: '확인 필요' },
];

const resultLabels: Record<Analysis['status'], string> = {
  exact: '동일 상품 확인',
  'needs-confirmation': '추가 확인이 필요해요',
  label: '세탁 라벨 판독',
};

export default function GarmentScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const { garments, ready, loadError } = useLaundry();
  const existing = garments.find((garment) => garment.id === id);

  if (!ready || loadError) {
    return (
      <EditorPage title={id ? '옷 수정' : '옷 추가'}>
        <Screen reserveTabBar={false}>
          <Notice tone={loadError ? 'error' : 'info'}>
            {loadError ?? '옷장을 불러오는 중이에요.'}
          </Notice>
        </Screen>
      </EditorPage>
    );
  }

  if (id && !existing) {
    return (
      <EditorPage title="옷 정보">
        <Screen reserveTabBar={false}>
          <Notice tone="error">옷장에서 의류를 찾지 못했어요.</Notice>
          <Button onPress={() => router.navigate('/wardrobe')}>옷장으로 돌아가기</Button>
        </Screen>
      </EditorPage>
    );
  }

  return (
    <EditorPage title={existing ? '옷 수정' : '옷 추가'}>
      <GarmentEditor key={id ?? 'new'} existing={existing} />
    </EditorPage>
  );
}

function EditorPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={local.editorPage}>
      <ScreenHeader
        title={title}
        onBack={() => router.canGoBack() ? router.back() : router.replace('/')}
      />
      {children}
    </View>
  );
}

function GarmentEditor({ existing }: { existing?: Garment }) {
  const { saveGarment, addToBasket, basketIds } = useLaundry();
  const { height: viewportHeight } = useWindowDimensions();
  const [draft, setDraft] = useState<GarmentDraft>(() => existing ?? { ...blankGarment });
  const [maxTemp, setMaxTemp] = useState(draft.maxTemp === null ? '' : String(draft.maxTemp));
  const [mode, setMode] = useState<EntryMode>(existing ? 'details' : 'clothing');
  const [uploads, setUploads] = useState<Partial<Record<PhotoKind, UploadPhoto>>>({});
  const [originalPhoto, setOriginalPhoto] = useState<UploadPhoto>();
  const [results, setResults] = useState<Partial<Record<PhotoKind, Analysis>>>({});
  const [analysisErrors, setAnalysisErrors] = useState<Partial<Record<PhotoKind, string>>>({});
  const [busy, setBusy] = useState('');
  const [photoError, setPhotoError] = useState('');
  const [cameraDenied, setCameraDenied] = useState(false);
  const [formError, setFormError] = useState('');
  const [fieldError, setFieldError] = useState<InvalidField>();
  const [addAfterSave, setAddAfterSave] = useState(false);
  const inProgress = useRef(false);
  const savedId = useRef(existing?.id);
  const nameInput = useRef<TextInputInstance>(null);
  const temperatureInput = useRef<TextInputInstance>(null);
  const pendingFocus = useRef<InvalidField | undefined>(undefined);
  useEffect(() => {
    const field = pendingFocus.current;
    pendingFocus.current = undefined;
    if (mode === 'details' && field) (field === 'name' ? nameInput : temperatureInput).current?.focus();
  }, [mode]);
  const photo = mode === 'clothing' ? uploads.clothing?.uri ?? draft.photo : draft.labelPhoto;
  const balancePhotoLayout = mode !== 'details' && !photo && !photoError && !cameraDenied;
  const photoTopOffset = balancePhotoLayout
    ? Math.min(64, Math.max(0, (viewportHeight - 700) / 2))
    : 0;

  function updateDraft(changes: Partial<GarmentDraft>) {
    setDraft((previous) => ({ ...previous, ...changes }));
    setFormError('');
  }

  async function choosePhoto(kind: PhotoKind, fromCamera: boolean) {
    if (inProgress.current) return;
    inProgress.current = true;
    setBusy('picker');
    setPhotoError('');
    setCameraDenied(false);
    try {
      if (fromCamera && Platform.OS !== 'web') {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setCameraDenied(true);
          return;
        }
      }

      const result = fromCamera
        ? await ImagePicker.launchCameraAsync(photoOptions)
        : await ImagePicker.launchImageLibraryAsync(photoOptions);
      if (result.canceled) return;

      const asset = result.assets[0];
      if (!asset.base64) throw new Error('Missing image data');
      const { uri } = asset;
      setUploads((previous) => ({ ...previous, [kind]: asset }));
      if (kind === 'clothing') {
        const followingUp = results.clothing?.followUp === 'clothing' || (!results.clothing && originalPhoto);
        if (followingUp && draft.photo) {
          setOriginalPhoto(originalPhoto ?? uploads.clothing ?? { uri: draft.photo });
        } else {
          setOriginalPhoto(undefined);
          updateDraft({ photo: uri });
        }
      } else {
        updateDraft({ labelPhoto: uri });
      }
      setResults((previous) => ({ ...previous, [kind]: undefined }));
      setAnalysisErrors((previous) => ({ ...previous, [kind]: undefined }));
    } catch {
      setPhotoError('사진을 열지 못했어요. 사진 보관함에서 다시 선택하거나 정보를 직접 입력해 주세요.');
    } finally {
      inProgress.current = false;
      setBusy('');
    }
  }

  async function analyze(kind: PhotoKind, uri: string) {
    if (inProgress.current) return;
    inProgress.current = true;
    setBusy(kind);
    setAnalysisErrors((previous) => ({ ...previous, [kind]: undefined }));
    try {
      const result = await analyzePhoto(kind, uploads[kind] ?? { uri }, Platform.OS === 'web');
      setResults((previous) => ({ ...previous, [kind]: result }));
    } catch (error) {
      setAnalysisErrors((previous) => ({
        ...previous,
        [kind]: error instanceof Error ? error.message : '사진을 분석하지 못했어요. 다시 시도해 주세요.',
      }));
    } finally {
      inProgress.current = false;
      setBusy('');
    }
  }

  function rememberIdentity({ care }: Analysis) {
    setDraft((previous) => ({
      ...previous,
      name: previous.name || care.name || care.category || '',
      category: previous.category || care.category || '',
      color: previous.color || care.color || '',
    }));
  }

  function applyResult(analysis: Analysis) {
    const { care } = analysis;
    setMaxTemp(care.maxTemp == null ? '' : String(care.maxTemp));
    setDraft((previous) => applyCare(previous, care));
    setFormError('');
    setFieldError(undefined);
    setMode('details');
  }

  /** 분석 결과를 적용해 바로 저장한다. 저장할 수 없는 값이면 직접 입력 화면에서 고치게 한다. */
  async function saveAnalysis(analysis: Analysis) {
    const next = applyCare(draft, analysis.care);
    const temperature = analysis.care.maxTemp == null ? '' : String(analysis.care.maxTemp);
    const invalid = await save(false, { draft: next, temperature });
    if (invalid) {
      applyResult(analysis);
      setFieldError(invalid);
      pendingFocus.current = invalid;
    }
  }

  /** 저장하면 undefined, 검증에 걸리면 해당 입력칸을 돌려준다. */
  async function save(add: boolean, explicit?: { draft: GarmentDraft; temperature: string }): Promise<InvalidField | undefined> {
    if (inProgress.current) return;
    setFormError('');
    const target = explicit?.draft ?? draft;
    const name = target.name.trim();
    const temperature = (explicit?.temperature ?? maxTemp).trim();
    const requiresTemp = target.wash === 'machine' || target.wash === 'hand';
    if (!name) {
      setFieldError('name');
      if (!explicit) nameInput.current?.focus();
      return 'name';
    }
    if (requiresTemp && temperature && (!/^\d{1,3}$/.test(temperature) || Number(temperature) > 100)) {
      setFieldError('temperature');
      if (!explicit) temperatureInput.current?.focus();
      return 'temperature';
    }
    setFieldError(undefined);
    if (add && basketIds.length >= basketLimit) {
      setFormError(`한 번에 ${basketLimit}벌까지 분석할 수 있어요. ‘드럼에도 담기’를 해제하면 옷장에 저장할 수 있어요.`);
      return;
    }

    inProgress.current = true;
    setBusy('save');
    try {
      const photos: GarmentPhotos = {};
      const clothing = [originalPhoto, uploads.clothing].find((photo) => photo?.uri === target.photo && photo?.base64);
      if (clothing?.base64) photos.clothing = clothing.base64;
      if (uploads.label?.base64) photos.label = uploads.label.base64;
      if (Object.values(photos).some((value) => value.length > 16 * 1024 * 1024)) {
        throw new Error('사진 한 장당 12MB 이하로 다시 선택해 주세요.');
      }
      const garment = await saveGarment({
        ...target,
        name,
        category: target.category.trim(),
        color: target.color.trim(),
        material: target.material.trim(),
        drying: target.drying.trim(),
        maxTemp: requiresTemp && temperature ? Number(temperature) : null,
      }, savedId.current, Object.keys(photos).length ? photos : undefined);
      savedId.current = garment.id;
      setDraft(garment);
      setUploads({});
      setOriginalPhoto(undefined);
      if (add) {
        const omitted = addToBasket([garment.id]);
        if (omitted === 0) {
          router.navigate('/drum');
          return;
        }
        setFormError('의류는 저장했어요. 드럼이 가득 차서 추가하지 못했어요.');
        return;
      }
      router.navigate('/wardrobe');
    } catch (error) {
      setFormError(error instanceof Error ? error.message : '의류를 저장하지 못했어요. 다시 시도해 주세요.');
    } finally {
      inProgress.current = false;
      setBusy('');
    }
  }

  return (
    <Screen
      key={mode}
      reserveTabBar={false}
      contentStyle={balancePhotoLayout
        ? [local.photoContent, { paddingTop: 16 + photoTopOffset }]
        : undefined}
    >
      <View style={local.intro}>
        {existing && <Text style={local.pageSubtitle}>{existing.name}</Text>}
        <View style={local.modeBar}>
          {entryModes.map(({ id, title, icon }) => {
            const selected = mode === id;
            const iconBackground = id === 'clothing' ? palette.aqua : id === 'label' ? palette.lilac : palette.blue;
            return (
              <Pressable
                key={id}
                accessibilityRole="tab"
                accessibilityLabel={title}
                accessibilityState={{ selected, disabled: Boolean(busy) }}
                disabled={Boolean(busy)}
                onPress={() => setMode(id)}
                style={({ pressed }) => [local.modeTab, selected && local.modeSelected, pressed && local.pressed]}
              >
                <View style={[local.modeIcon, { backgroundColor: selected ? palette.surface : iconBackground }]} accessible={false}>
                  <Ionicons name={icon} size={20} color={palette.accent} />
                </View>
                <Text style={[local.modeLabel, selected && local.modeLabelSelected]}>{title}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      {mode !== 'details' ? (
        <View style={[local.photoStack, !photo && local.photoStackGrow]}>
          {cameraDenied && (
            <View style={styles.section}>
              <Notice tone="error">카메라 권한이 필요해요. 사진을 선택하거나 정보를 직접 입력할 수 있어요.</Notice>
              <Button
                tone="quiet"
                icon="settings-outline"
                onPress={() => void Linking.openSettings().catch(() => setPhotoError('기기 설정에서 카메라 권한을 변경할 수 있어요.'))}
              >
                기기 설정 열기
              </Button>
            </View>
          )}
          {photoError ? <Notice tone="error">{photoError}</Notice> : null}
          <PhotoEntry
            kind={mode}
            uri={photo}
            busy={Boolean(busy)}
            saving={busy === 'save'}
            analyzing={busy === mode}
            result={results[mode]}
            recommendation={results[mode] && <MachineRecommendation care={applyCare(draft, results[mode].care)} />}
            error={analysisErrors[mode]}
            onCamera={() => void choosePhoto(mode, true)}
            onLibrary={() => void choosePhoto(mode, false)}
            onAnalyze={() => photo && void analyze(mode, photo)}
            onApply={(result) => void saveAnalysis(result)}
            onNext={(result) => {
              rememberIdentity(result);
              if (result.followUp === mode) {
                void choosePhoto(mode, false);
                return;
              }
              setMode(result.followUp ?? 'details');
            }}
          />
          {formError ? <Notice tone="error">{formError}</Notice> : null}
          {photo && (
            <Button tone="quiet" icon="arrow-forward-outline" disabled={Boolean(busy)} onPress={() => {
              const result = results[mode];
              if (result && result.status !== 'needs-confirmation') applyResult(result);
              else {
                if (result) rememberIdentity(result);
                setMode('details');
              }
            }}>
              {results[mode] && results[mode].status !== 'needs-confirmation' ? '저장 전에 정보 수정' : '옷 정보 입력'}
            </Button>
          )}
        </View>
      ) : (
        <View style={local.formStack}>
          {draft.photo && <PhotoStrip uri={draft.photo} title="의류 사진" status="옷장에 함께 저장돼요." />}
          {draft.labelPhoto && <PhotoStrip uri={draft.labelPhoto} title="세탁 라벨 사진" status="옷장에 함께 저장돼요." />}
          <FormSection title="의류 정보" icon="shirt-outline">
            <View style={local.fieldGroup}>
              <Field
                inputRef={nameInput}
                invalid={fieldError === 'name'}
                label="의류 이름"
                value={draft.name}
                placeholder="예: 흰색 면 티셔츠"
                onChangeText={(name) => {
                  updateDraft({ name });
                  if (fieldError === 'name') setFieldError(undefined);
                }}
              />
              {fieldError === 'name' && <FieldError>옷장에서 사용할 이름을 입력해 주세요.</FieldError>}
            </View>
            <View style={local.fieldPair}>
              <View style={local.fieldColumn}>
                <Field label="종류" value={draft.category} placeholder="예: 티셔츠" onChangeText={(category) => updateDraft({ category })} />
              </View>
              <View style={local.fieldColumn}>
                <Field label="색상" value={draft.color} placeholder="예: 흰색" onChangeText={(color) => updateDraft({ color })} />
              </View>
            </View>
            <Field
              label="소재 및 혼용률"
              value={draft.material}
              placeholder="예: 면 100%"
              onChangeText={(material) => updateDraft({ material, source: 'manual' })}
            />
          </FormSection>

          <FormSection title="세탁 조건" icon="water-outline" caption={`출처 · ${careSources[draft.source]}`}>
            <ChoiceGrid
              label="세탁 방법"
              options={washOptions}
              value={draft.wash}
              onSelect={(wash) => {
                updateDraft({ wash, source: 'manual' });
                if (fieldError === 'temperature' && (wash === 'none' || wash === 'unknown')) setFieldError(undefined);
              }}
            />
            {(draft.wash === 'machine' || draft.wash === 'hand') && (
              <View style={local.fieldGroup}>
                <Field
                  inputRef={temperatureInput}
                  invalid={fieldError === 'temperature'}
                  label="최대 세탁 온도 (°C)"
                  value={maxTemp}
                  keyboardType="number-pad"
                  placeholder="모르면 비워 두세요"
                  onChangeText={(value) => {
                    setMaxTemp(value);
                    updateDraft({ source: 'manual' });
                    if (fieldError === 'temperature') setFieldError(undefined);
                  }}
                />
                {fieldError === 'temperature' && <FieldError>0~100 사이의 정수로 입력해 주세요.</FieldError>}
              </View>
            )}
            {draft.wash === 'machine' && (
              <ChoiceGrid
                label="세탁 강도"
                options={cycleOptions}
                value={draft.washStrength ?? (draft.gentle === null ? 'unknown' : draft.gentle ? 'gentle' : 'normal')}
                onSelect={(cycle) => updateDraft({
                  gentle: cycle === 'unknown' ? null : cycle !== 'normal',
                  washStrength: cycle === 'unknown' ? null : cycle,
                  source: 'manual',
                })}
                compact
              />
            )}
            {draft.wash === 'machine' && (
              <CheckRow label="단독 세탁 필요" checked={draft.washSeparately === true} disabled={Boolean(busy)}
                onPress={() => updateDraft({ washSeparately: !draft.washSeparately })} />
            )}
          </FormSection>

          <FormSection title="건조 조건" icon="sunny-outline">
            <ChoiceGrid
              label="건조기 사용"
              options={dryerOptions}
              value={draft.dryer}
              compact
              onSelect={(dryer) => updateDraft({ dryer, source: 'manual' })}
            />
            <Field
              label="자연건조 방법"
              value={draft.drying}
              placeholder="예: 그늘에서 뉘어 말리기"
              onChangeText={(drying) => updateDraft({ drying, source: 'manual' })}
            />
          </FormSection>

          <MachineRecommendation care={{
            ...draft,
            maxTemp: /^\d{1,3}$/.test(maxTemp.trim()) && Number(maxTemp) <= 100 ? Number(maxTemp) : null,
          }} />

          <View style={local.saveArea}>
            {!existing && (
              <CheckRow
                label="드럼에도 담기"
                checked={addAfterSave}
                disabled={Boolean(busy)}
                onPress={() => {
                  setAddAfterSave((previous) => !previous);
                  setFormError('');
                }}
              />
            )}
            {formError ? <Notice tone="error">{formError}</Notice> : null}
            <Button icon="checkmark-outline" disabled={Boolean(busy)} onPress={() => void save(addAfterSave)}>
              {busy === 'save' ? '저장 중…' : addAfterSave ? '저장하고 드럼으로' : '옷장에 저장'}
            </Button>
          </View>
        </View>
      )}
    </Screen>
  );
}

/** 분석 결과의 세탁 정보를 옷 정보에 합친 새 값. */
function applyCare(draft: GarmentDraft, care: Analysis['care']): GarmentDraft {
  return {
    ...draft,
    name: draft.name || care.name || care.category || '',
    category: draft.category || care.category || '',
    color: draft.color || care.color || '',
    material: care.material ?? '',
    wash: care.wash ?? 'unknown',
    maxTemp: care.maxTemp ?? null,
    gentle: care.gentle ?? null,
    washStrength: care.washStrength ?? null,
    maxSpin: care.maxSpin ?? null,
    dryer: care.dryer ?? 'unknown',
    drying: care.drying ?? '',
    careNotes: care.careNotes,
    source: care.source ?? 'manual',
    sourceReference: care.sourceReference,
  };
}

function MachineRecommendation({ care }: { care: GarmentDraft }) {
  const { machine } = useLaundry();
  const guide = machine && care.wash === 'machine' ? machineGuide([{ ...care, id: 'draft' }], machine) : null;
  let body: ReactNode;
  if (!machine) {
    body = (
      <>
        <Text style={styles.muted}>세탁기를 등록하면 내 세탁기에 맞는 코스를 추천해 드려요.</Text>
        <Button tone="quiet" icon="options-outline" onPress={() => router.navigate('/machines')}>세탁기 등록하기</Button>
      </>
    );
  } else if (care.wash === 'none' || care.wash === 'hand') {
    return null;
  } else if (care.wash === 'unknown') {
    body = <Text style={styles.muted}>기계세탁 가능 여부를 라벨에서 확인하면 코스를 추천해 드려요.</Text>;
  } else if (!guide) {
    body = <Text style={styles.muted}>이 세탁기에서 옷에 맞는 확인된 설정을 찾지 못했어요. 라벨과 설명서를 확인해 주세요.</Text>;
  } else {
    body = <MachineGuideBody machine={machine} guide={guide} />;
  }
  return (
    <View style={[styles.card, local.recommendation]}>
      <Text accessibilityRole="header" style={styles.title}>내 세탁기 추천 코스</Text>
      {body}
    </View>
  );
}

function FormSection({ title, icon, caption, children }: {
  title: string;
  icon: 'shirt-outline' | 'water-outline' | 'sunny-outline';
  caption?: string;
  children: ReactNode;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.cardContent}>
        <View style={local.sectionHeader}>
          <View style={styles.iconBadge}>
            <Ionicons name={icon} size={18} color={palette.accent} />
          </View>
          <View style={local.sectionHeading}>
            <Text accessibilityRole="header" style={styles.rowTitle}>{title}</Text>
            {caption ? <Text style={styles.rowMeta}>{caption}</Text> : null}
          </View>
        </View>
        {children}
      </View>
    </View>
  );
}

function FieldError({ children }: { children: string }) {
  return <Text accessibilityLiveRegion="polite" style={local.fieldError}>{children}</Text>;
}

function ChoiceGrid<T extends string>({ label, options, value, compact, onSelect }: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  compact?: boolean;
  onSelect: (value: T) => void;
}) {
  return (
    <View style={local.fieldGroup}>
      <Text style={local.fieldLabel}>{label}</Text>
      <View style={local.choiceGrid}>
        {options.map((option) => {
          const checked = value === option.value;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityState={{ checked }}
              onPress={() => onSelect(option.value)}
              style={({ pressed }) => [
                local.choice,
                compact && local.compactChoice,
                checked && local.choiceChecked,
                pressed && local.pressed,
              ]}
            >
              <View style={[local.radio, checked && local.radioChecked]}>
                {checked && <View style={local.radioDot} />}
              </View>
              <Text style={[local.choiceLabel, checked && local.choiceLabelChecked]}>{option.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function CheckRow({ label, checked, disabled, onPress }: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [local.checkRow, pressed && local.pressed]}
    >
      <View style={[local.checkbox, checked && local.checkboxChecked]}>
        {checked && <Ionicons name="checkmark" size={16} color={palette.inverse} />}
      </View>
      <Text style={local.fieldLabel}>{label}</Text>
    </Pressable>
  );
}

function PhotoEntry({
  kind, uri, busy, saving, analyzing, result, recommendation, error, onCamera, onLibrary, onAnalyze, onApply, onNext,
}: {
  kind: PhotoKind;
  uri?: string;
  busy: boolean;
  saving: boolean;
  analyzing: boolean;
  result?: Analysis;
  recommendation?: ReactNode;
  error?: string;
  onCamera: () => void;
  onLibrary: () => void;
  onAnalyze: () => void;
  onApply: (result: Analysis) => void;
  onNext: (result: Analysis) => void;
}) {
  const { title, icon, guide } = photoCopy[kind];
  const report = analyzing || error ? undefined : result;
  return (
    <View style={[local.photoEntry, !uri && local.photoEntryGrow]}>
      {uri && report ? (
        <>
          <PhotoStrip uri={uri} title={title} status="분석 완료">
            <Button tone="quiet" disabled={busy} onPress={onAnalyze}>다시 분석</Button>
          </PhotoStrip>
          <AnalysisReport result={report} kind={kind} busy={busy} saving={saving} onApply={onApply} onNext={onNext} />
          {recommendation}
        </>
      ) : (
        <>
          <View style={[local.captureStage, !uri && local.captureEmpty]}>
            {!uri && (
              <View pointerEvents="none" style={StyleSheet.absoluteFill}>
                <View style={local.captureAccentTop} />
                <View style={local.captureAccentBottom} />
              </View>
            )}
            {uri ? (
              <Image accessibilityLabel={title} source={{ uri }} style={local.preview} />
            ) : (
              <View style={local.captureMessage}>
                <View style={local.captureHalo} accessible={false}>
                  <View style={local.captureSymbol}>
                    <Ionicons name={icon} size={40} color={palette.accent} />
                  </View>
                </View>
                <Text style={local.captureGuide}>{guide}</Text>
              </View>
            )}
          </View>
          {error ? <Notice tone="error">{error}</Notice> : null}
          {uri && analyzing ? (
            <LaundryLoading label={kind === 'label' ? '세탁 라벨의 표시를 읽고 있어요.' : '옷의 종류와 관리 정보를 살펴보고 있어요.'} />
          ) : uri ? (
            <Button icon="scan-outline" disabled={busy} onPress={onAnalyze}>
              {error ? '분석 다시 시도' : '사진 분석'}
            </Button>
          ) : null}
        </>
      )}
      <PhotoControls selected={Boolean(uri)} busy={busy} onCamera={onCamera} onLibrary={onLibrary} />
    </View>
  );
}

function PhotoControls({ selected, busy, onCamera, onLibrary }: {
  selected: boolean;
  busy: boolean;
  onCamera: () => void;
  onLibrary: () => void;
}) {
  return (
    <View style={local.captureControls}>
      <View style={local.photoActions}>
        <View style={local.action}>
          <Button tone={selected ? 'quiet' : 'primary'} icon="camera-outline" disabled={busy} onPress={onCamera}>
            {selected ? '다시 촬영' : '촬영'}
          </Button>
        </View>
        <View style={local.action}>
          <Button tone={selected ? 'quiet' : 'secondary'} icon="images-outline" disabled={busy} onPress={onLibrary}>
            {selected ? '다른 사진 선택' : '사진 선택'}
          </Button>
        </View>
      </View>
      <View style={local.privacy}>
        <Ionicons name="lock-closed-outline" size={13} color={palette.muted} />
        <Text style={local.caption}>분석하거나 옷장에 저장할 때 사진을 WashWise 서버로 보내요.</Text>
      </View>
    </View>
  );
}

function PhotoStrip({ uri, title, status, children }: {
  uri: string;
  title: string;
  status: string;
  children?: ReactNode;
}) {
  return (
    <View style={[styles.card, local.photoStrip]}>
      <Image accessibilityLabel={title} source={{ uri }} style={local.thumbnail} />
      <View style={local.photoStripCopy}>
        <Text style={local.fieldLabel}>{title}</Text>
        <Text style={local.caption}>{status}</Text>
      </View>
      {children}
    </View>
  );
}

function AnalysisReport({ result, kind, busy, saving, onApply, onNext }: {
  result: Analysis;
  kind: PhotoKind;
  busy: boolean;
  saving: boolean;
  onApply: (result: Analysis) => void;
  onNext: (result: Analysis) => void;
}) {
  const { care } = result;
  const matchedWithoutCare = result.status === 'exact' && !result.hasPublishedCare;
  const nextLabel = result.followUp === 'label'
    ? (kind === 'label' ? '라벨 사진 다시 선택' : '세탁 라벨 촬영')
    : result.followUp === 'clothing' ? '추가 사진 선택' : '직접 입력';
  const reportTone = result.status === 'needs-confirmation' ? palette.lilac : palette.aqua;
  const showsTips = result.status === 'label'
    ? result.materialGuidance.length > 0
    : Boolean(result.guidance.length || result.materialGuidance.length);
  const labelTips = result.status === 'label' && result.materialGuidance.length > 0;
  const noCareMessage = '세탁 정보를 확실하게 알 수 없어요. 세탁 라벨을 찍어주세요.';
  const materialLabelPrompt = '더 확실하게 알고 싶으면 세탁 라벨을 찍어주세요.';
  const canApply = result.status !== 'needs-confirmation';
  const cells = result.status === 'label' ? careSummary(care, result.waterText) : [];
  const bullets = splitGuidance(result.guidance);
  const note = result.materialGuidance.length > 0 && !labelTips
    ? undefined
    : matchedWithoutCare ? noCareMessage
      : bullets.length === 0 && cells.length === 0
        ? messageWithoutFollowUp(result.message, result.followUpInstructions) || undefined
        : undefined;
  const followUpText = matchedWithoutCare || (result.materialGuidance.length > 0 && !labelTips) ? undefined
    : result.status === 'exact' && !(showsTips && result.followUp === 'label') ? undefined
      : result.followUpInstructions;
  const applyButton = canApply && (
    <Button icon="checkmark-outline" disabled={busy} onPress={() => onApply(result)}>
      {saving ? '저장 중…' : '옷장에 저장'}
    </Button>
  );
  const nextButton = (result.followUp || !canApply) && (
    <Button tone={canApply ? 'secondary' : 'primary'} icon="arrow-forward-outline" disabled={busy} onPress={() => onNext(result)}>
      {nextLabel}
    </Button>
  );
  return (
    <View style={[local.report, { backgroundColor: reportTone }]}>
      <View style={local.reportHeading} accessibilityLiveRegion="polite">
        <View style={local.reportIcon}><Ionicons name="scan-outline" size={23} color={palette.accent} /></View>
        <Text accessibilityRole="header" style={local.reportTitle}>
          {result.estimated ? '옷 종류에 맞춘 일반 관리 팁' : matchedWithoutCare ? '상품을 찾았어요' : resultLabels[result.status]}
        </Text>
        {result.estimated && result.searchNote && <Text style={local.caption}>{result.searchNote}</Text>}
        {care.name && <Text style={local.fieldLabel}>{care.name}</Text>}
        {result.productCode && <Text style={local.caption}>{[result.productCode, care.color].filter(Boolean).join(' · ')}</Text>}
        {care.material && <Text style={local.caption}>{care.material}</Text>}
      </View>
      <View style={local.reportPending}>
        {cells.length > 0 && (
          <>
            <Text style={local.fieldLabel}>읽은 정보</Text>
            <View style={local.summaryCells}>
              {cells.map(({ label, value }) => (
                <View key={label} style={local.summaryCell} accessible accessibilityLabel={`${label} ${value}`}>
                  <Text style={local.caption}>{label}</Text>
                  <Text style={local.summaryValue}>{value}</Text>
                </View>
              ))}
            </View>
          </>
        )}
        {bullets.length > 0 && (
          <>
            <Text style={local.fieldLabel}>{result.status === 'exact' ? `${result.sourceLabel}에서 확인한 안내` : '관리 안내'}</Text>
            {bullets.map((line, index) => <Text key={`${line}-${index}`} style={styles.body}>• {line}</Text>)}
          </>
        )}
        {showsTips && result.materialGuidance.length > 0 && (
          <View style={local.estimatedPanel}>
            <Text style={local.fieldLabel}>소재 기반 참고 안내 · 임시 추정</Text>
            {result.materialGuidance.map((line, index) => {
              const item = parseMaterialGuidance(line);
              return (
                <View key={`${line}-${index}`} style={local.materialTip}>
                  {item ? (
                    <View style={local.materialTipLabeled}>
                      <View accessible={false} style={local.materialTipBullet} />
                      <View style={local.materialTipContent}>
                        <Text style={local.materialTipLabel}>{item.label}</Text>
                        <Text style={styles.body}>{item.instruction}</Text>
                      </View>
                    </View>
                  ) : <Text style={styles.body}>{line}</Text>}
                </View>
              );
            })}
            {kind !== 'label' && <Text style={local.estimatedPrompt}>{materialLabelPrompt}</Text>}
          </View>
        )}
        {note && <Text style={styles.body}>{note}</Text>}
        {followUpText && (
          <View style={local.estimatedPanel}>
            <Text style={local.fieldLabel}>더 정확하게 읽으려면</Text>
            <Text style={styles.body}>{followUpText}</Text>
          </View>
        )}
      </View>
      {result.sourceUrl && (
        <Button tone="quiet" icon="open-outline" onPress={() => void Linking.openURL(result.sourceUrl!).catch(() => {})}>
          {result.sourceLabel}
        </Button>
      )}
      {canApply ? <>{applyButton}{nextButton}</> : nextButton}
    </View>
  );
}

const local = StyleSheet.create({
  editorPage: { flex: 1 },
  intro: { gap: 8 },
  pageSubtitle: { color: palette.muted, fontSize: 14, lineHeight: 20 },
  modeBar: { flexDirection: 'row', gap: 8 },
  modeTab: {
    flex: 1, alignItems: 'center', justifyContent: 'center', gap: 5,
    minHeight: 76, paddingHorizontal: 4, paddingVertical: 7, borderRadius: 16,
    borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface,
  },
  modeSelected: { borderColor: palette.accent, backgroundColor: palette.accent },
  modeIcon: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center', borderRadius: 11 },
  modeLabel: { flexShrink: 1, color: palette.ink, textAlign: 'center', fontSize: 12, fontWeight: '700' },
  modeLabelSelected: { color: palette.inverse },
  pressed: { opacity: 0.65 },

  photoContent: { flexGrow: 1 },
  photoStack: { gap: 10 },
  photoStackGrow: { flexGrow: 1 },
  formStack: { gap: 12 },
  photoEntry: { gap: 10 },
  photoEntryGrow: { flexGrow: 1 },
  captureStage: {
    alignItems: 'center', justifyContent: 'center', borderRadius: 18, overflow: 'hidden',
    borderWidth: 1, borderColor: palette.line, backgroundColor: palette.lilac,
  },
  captureAccentTop: {
    position: 'absolute', top: 18, right: 18, width: 118, height: 118, borderRadius: 59,
    borderWidth: 1, borderColor: palette.surface, backgroundColor: palette.accentWash, opacity: 0.55,
  },
  captureAccentBottom: {
    position: 'absolute', bottom: -30, left: 16, width: 88, height: 88, borderRadius: 44,
    borderWidth: 7, borderColor: palette.surface, opacity: 0.55,
  },
  captureEmpty: {
    flexGrow: 1, minHeight: 145, maxHeight: 455, justifyContent: 'space-between', gap: 8, padding: 14,
  },
  captureMessage: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8 },
  captureControls: { alignSelf: 'stretch', gap: 8 },
  captureHalo: {
    width: 82, height: 82, borderRadius: 41, borderWidth: 1, borderColor: palette.surface,
    alignItems: 'center', justifyContent: 'center',
  },
  captureSymbol: {
    width: 68, height: 68, borderRadius: 34, alignItems: 'center', justifyContent: 'center',
    backgroundColor: palette.surface,
  },
  captureGuide: { color: palette.muted, maxWidth: 254, fontSize: 13, lineHeight: 19, textAlign: 'center' },
  preview: { height: 232, width: '100%', resizeMode: 'contain' },
  photoActions: { alignSelf: 'stretch', flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  action: { flex: 1, minWidth: 112 },
  privacy: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 },
  photoStrip: {
    minHeight: 66, flexDirection: 'row', alignItems: 'center', gap: 10,
    padding: 8,
  },
  thumbnail: { width: 52, height: 52, borderRadius: 11, resizeMode: 'contain', backgroundColor: palette.subtle },
  photoStripCopy: { flex: 1, gap: 2 },

  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  sectionHeading: { flex: 1, gap: 3 },
  caption: { color: palette.muted, fontSize: 12, lineHeight: 18 },
  fieldGroup: { gap: 6 },
  fieldLabel: { color: palette.ink, fontSize: 14, fontWeight: '700' },
  fieldPair: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  fieldColumn: { flex: 1, minWidth: 110 },
  fieldError: { color: palette.error, fontSize: 13, lineHeight: 19, fontWeight: '600' },
  choiceGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  choice: {
    flexBasis: '45%', flexGrow: 1, flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 48,
    borderWidth: 1, borderColor: palette.line, borderRadius: 12, paddingHorizontal: 9, paddingVertical: 7,
    backgroundColor: palette.surface,
  },
  compactChoice: { flexBasis: '30%', minWidth: 88 },
  choiceChecked: { borderColor: palette.accent, backgroundColor: palette.accentWash },
  choiceLabel: { flex: 1, color: palette.ink, fontSize: 13, fontWeight: '600' },
  choiceLabelChecked: { color: palette.accent, fontWeight: '700' },
  radio: {
    width: 14, height: 14, borderRadius: 7, borderWidth: 1, borderColor: palette.muted,
    alignItems: 'center', justifyContent: 'center',
  },
  radioChecked: { borderColor: palette.accent },
  radioDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: palette.accent },
  checkRow: { minHeight: 44, alignItems: 'center', flexDirection: 'row', gap: 10, paddingHorizontal: 3 },
  checkbox: {
    width: 20, height: 20, borderWidth: 1, borderColor: palette.muted, borderRadius: 6,
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: palette.accent, borderColor: palette.accent },
  recommendation: { padding: 13, gap: 10 },
  saveArea: { gap: 8, padding: 10, borderRadius: 16, backgroundColor: palette.accentWash },

  report: { gap: 11, borderWidth: 1, borderColor: palette.line, borderRadius: 18, padding: 13 },
  reportHeading: { alignItems: 'center', gap: 5 },
  reportIcon: {
    width: 43, height: 43, alignItems: 'center', justifyContent: 'center',
    backgroundColor: palette.surface, borderRadius: 14, marginBottom: 2,
  },
  reportTitle: { color: palette.ink, fontSize: 19, fontWeight: '800', textAlign: 'center' },
  reportPending: { backgroundColor: palette.surface, padding: 11, borderRadius: 12, gap: 8 },
  summaryCells: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  summaryCell: { flexGrow: 1, flexBasis: 90, minWidth: 90, gap: 2, padding: 10, borderRadius: 12, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface },
  summaryValue: { color: palette.ink, fontSize: 15, lineHeight: 21, fontWeight: '800' },
  estimatedPanel: { gap: 7, padding: 11, borderRadius: 12, backgroundColor: palette.subtle },
  materialTip: { gap: 2, paddingBottom: 4 },
  materialTipLabeled: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  materialTipBullet: { width: 6, height: 6, marginTop: 9, borderRadius: 3, backgroundColor: palette.accent },
  materialTipContent: { flex: 1, gap: 2 },
  materialTipLabel: { color: palette.accent, fontSize: 17, lineHeight: 24, fontWeight: '800' },
  estimatedPrompt: { color: palette.accent, fontSize: 13, lineHeight: 19, fontWeight: '700' },
});
