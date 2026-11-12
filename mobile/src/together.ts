import type { Course, Garment, Machine, VerifiedSetting } from './model';

/** 선택한 옷을 한 번에 빨 때의 계획. 저장된 옷 정보만으로 계산하고 세탁기 모델과는 무관하다. */
export type TogetherPlan = {
  /** 세탁기에 함께 넣으면 안 되는 옷 */
  apart: { garment: Garment; reason: string }[];
  pending: { garment: Garment; reason: string }[];
  /** 서로 같이 빨면 안 되는 조합 */
  conflicts: { first: Garment[]; second: Garment[]; reason: string }[];
  /** 나눠 빨기 제안. 한 묶음이면 모두 함께 빨 수 있다. */
  loads: { garments: Garment[]; label: string; advice: string }[];
  /** 함께 빨 때 지킬 점 */
  cautions: string[];
  /** 옷마다 따로 챙길 점 */
  notes: { garment: Garment; lines: string[] }[];
  /** 옷마다 라벨 안내 중 건조에 관한 줄. 건조 안내에서 보여 준다. */
  dryingNotes: { garment: Garment; lines: string[] }[];
};

export type ColorFamily = 'light' | 'deep' | 'unknown';

const lightTone = /연한|연(핑크|분홍|회색|그레이|베이지|블루|하늘|노랑|보라)|라이트|파스텔|light|pastel|pale/;
const deepTone = /진한|진(청|회색|그레이|녹색|초록|남색|갈색)|다크|dark|deep/;
const lightColor = /흰|화이트|하양|하얀|아이보리|크림|베이지|오트밀|에크루|white|ivory|cream|beige|ecru/;
const deepColor = new RegExp([
  '검|블랙|네이비|남색|차콜|브라운|갈색|카키|버건디|와인',
  '빨|레드|파랑|파란|블루|초록|녹색|그린|노랑|노란|옐로|보라|퍼플|핑크|분홍|주황|오렌지|회색|그레이|청|인디고',
  'black|navy|charcoal|brown|khaki|burgundy|red|blue|green|yellow|purple|pink|orange|gr[ae]y|indigo',
].join('|'));

/** 이염 기준의 색 분류. 색이 진하거나 선명하면 deep. */
export function colorFamily(color: string): ColorFamily {
  const families = color.split(/[/,·&]/).map(singleColorFamily);
  if (families.includes('deep')) return 'deep';
  return families.includes('light') ? 'light' : 'unknown';
}

function singleColorFamily(color: string): ColorFamily {
  const value = color.trim().toLowerCase();
  if (!value) return 'unknown';
  if (lightTone.test(value)) return 'light';
  if (deepTone.test(value)) return 'deep';
  if (lightColor.test(value)) return 'light';
  if (deepColor.test(value)) return 'deep';
  return 'unknown';
}

const text = (garment: Garment) => `${garment.name} ${garment.category} ${garment.material}`.toLowerCase();
const leather = /가죽|레더|스웨이드|모피|퍼\b|leather|suede|fur\b/;
const delicate = /울|모\s*\d|캐시미어|실크|견|레이스|레이온|비스코스|모달|앙고라|알파카|니트|스웨터|가디건|란제리|wool|cashmere|silk|lace|rayon|viscose|knit/;
const rough = /데님|청바지|진\b|jean|denim|지퍼|집업|재킷|자켓|점퍼|아우터|패딩|코트|jacket|zip/;
const lintGiver = /수건|타월|타올|플리스|기모|후리스|니트|스웨터|테리|towel|fleece|terry/;
const denim = /데님|청바지|jean|denim/;
const printed = /프린트|나염|그래픽|로고|자수|print|graphic/;
const fastened = /지퍼|집업|후크|단추|zip|button/;

const strengthUnknown = (garment: Garment) => garment.gentle == null && !garment.washStrength;
// 세탁 강도를 모르면 가장 안전한 약한 세탁으로 본다.
const isDelicate = (garment: Garment) => garment.gentle === true || strengthUnknown(garment)
  || garment.washStrength === 'gentle' || garment.washStrength === 'very_gentle' || delicate.test(text(garment));
const names = (garments: Garment[]) => garments.map(({ name }) => name).join(', ');
const isSolo = (garment: Garment) => garment.washSeparately === true || garment.colorBleedRisk === true;

function separationReason(first: Garment, second: Garment) {
  if (isSolo(first) || isSolo(second)) return '단독 세탁이 필요하거나 이염 우려가 있는 옷은 한 벌씩 따로 빨아 주세요.';
  const firstColor = colorFamily(first.color);
  const secondColor = colorFamily(second.color);
  if (firstColor === 'unknown' || secondColor === 'unknown') {
    return '색상을 확인하기 어려운 옷은 이염 여부를 확인할 때까지 따로 빨아 주세요.';
  }
  if (firstColor !== secondColor) return '밝은색 옷에 진한색 옷의 물이 들 수 있어요. 나눠서 빨아 주세요.';
  if ((isDelicate(first) && rough.test(text(second))) || (isDelicate(second) && rough.test(text(first)))) {
    return '약한 소재가 데님·지퍼 달린 옷에 쓸려 보풀이 생기거나 올이 나갈 수 있어요.';
  }
  if (firstColor === 'deep' && lintGiver.test(text(first)) !== lintGiver.test(text(second))) {
    return '보풀과 먼지가 진한색 옷에 붙을 수 있어요. 나눠서 빨아 주세요.';
  }
  return null;
}

export function planTogether(garments: Garment[], machine?: Machine | null): TogetherPlan {
  const apart: TogetherPlan['apart'] = [];
  const pending: TogetherPlan['pending'] = [];
  const washable: Garment[] = [];
  for (const garment of garments) {
    if (garment.wash === 'none') {
      apart.push({ garment, reason: '물세탁 금지 표시예요. 라벨에서 허용하는 관리 방법을 확인해 주세요.' });
    } else if (garment.wash === 'hand') {
      apart.push({ garment, reason: '손세탁 표시예요. 라벨을 보고 따로 손으로 빨아 주세요.' });
    } else if (leather.test(text(garment))) {
      apart.push({ garment, reason: '가죽·스웨이드·모피는 손상될 수 있어요. 라벨과 전문 세탁 방법을 확인해 주세요.' });
    } else if (garment.wash === 'unknown') {
      pending.push({ garment, reason: '라벨을 보고 기계세탁이 가능한지 확인해 주세요.' });
    } else {
      washable.push(garment);
    }
  }

  const conflicts: TogetherPlan['conflicts'] = [];
  const groups: Garment[][] = [];
  for (const [index, first] of washable.entries()) {
    const byReason = new Map<string, Garment[]>();
    for (const second of washable.slice(index + 1)) {
      const reason = separationReason(first, second);
      if (reason) byReason.set(reason, [...(byReason.get(reason) ?? []), second]);
    }
    for (const [reason, second] of byReason) conflicts.push({ first: [first], second, reason });

    const compatible = groups.find((group) => group.every((second) => !separationReason(first, second)));
    if (compatible) compatible.push(first);
    else groups.push([first]);
  }

  const colorLabels = { light: '밝은색', deep: '진한색', unknown: '색상 미확인 · 단독 세탁' };
  const loads = groups.flatMap((items) => {
    const makeLoad = (subset: Garment[], suffix = '') => {
      const gentle = subset.some(isDelicate);
      const veryGentle = subset.some(({ washStrength }) => washStrength === 'very_gentle');
      const label = isSolo(subset[0]) ? '단독 세탁' : colorLabels[colorFamily(subset[0].color)];
      const strength = veryGentle ? '매우 약한 세탁' : '약한 세탁';
      const spinLimits = subset.flatMap(({ maxSpin }) => maxSpin == null ? [] : [maxSpin]);
      const spin = spinLimits.length ? ` 탈수는 ${Math.min(...spinLimits)}rpm 이하로 맞추세요.` : '';
      return {
        garments: subset,
        label: `${label}${gentle ? ` · ${strength}` : ''}${suffix}`,
        advice: `${waterAdvice(subset)}${gentle ? ` ${strength}이 가능한 코스를 골라 주세요.` : ''}${subset.some(strengthUnknown) ? ' 세탁 강도 표시는 라벨에서 확인해 주세요.' : ''}${spin}`,
      };
    };
    const base = makeLoad(items);
    const wholeGuide = machine ? machineGuide(items, machine) : null;
    if (!machine || (wholeGuide && wholeGuide.checks.length === 0)
      || !machine.courses.some((course) => course.verifiedSettings?.length)) return [base];

    // Preserve the existing color/material groups, but divide a load if the
    // selected model has confirmed settings for smaller subsets.
    const supported: Garment[][] = [];
    const unresolved: Garment[] = [];
    for (const item of items) {
      const target = supported.find((candidate) => {
        const guide = machineGuide([...candidate, item], machine);
        return guide !== null && guide.checks.length === 0;
      });
      if (target) target.push(item);
      else {
        const individualGuide = machineGuide([item], machine);
        if (individualGuide && individualGuide.checks.length === 0) supported.push([item]);
        else unresolved.push(item);
      }
    }
    const split = supported.map((subset) => makeLoad(subset, subset.length === 1 ? ' · 모델 설정 확인' : ''));
    // 확인할 값이 남은 조건부 조합은 "찾지 못함"과 구분해 따로 묶는다.
    const conditional: Garment[][] = [];
    const missing: Garment[] = [];
    for (const item of unresolved) {
      if (!machineGuide([item], machine)) { missing.push(item); continue; }
      const target = conditional.find((candidate) => machineGuide([...candidate, item], machine) !== null);
      if (target) target.push(item);
      else conditional.push([item]);
    }
    for (const subset of conditional) split.push(makeLoad(subset, ' · 확인 후 사용'));
    if (missing.length) split.push({
      ...makeLoad(missing, missing.length === 1 ? ' · 설정 확인 필요' : ''),
      advice: `${makeLoad(missing).advice} 선택한 세탁기에서 이 옷에 맞는 확인된 조합을 찾지 못했어요. 설명서와 라벨을 확인해 주세요.`,
    });
    return split;
  });

  const cautions: string[] = [];
  const soft = washable.filter(isDelicate);
  if (loads.length === 1 && washable.length > 1) {
    cautions.push(waterAdvice(washable));
    if (soft.length && soft.length < washable.length) {
      cautions.push(`${names(soft)}에 맞춰 섬세 코스를 고르고 세탁망에 넣어 주세요.`);
    }
  }
  const noDryer = washable.filter((garment) => garment.dryer === 'no');
  const dryerOk = washable.filter((garment) => garment.dryer === 'yes');
  if (noDryer.length && dryerOk.length) {
    cautions.push(`건조기에는 ${names(dryerOk)}만 넣고, ${names(noDryer)}은(는) 꺼내서 자연건조하세요.`);
  } else if (noDryer.length) {
    cautions.push(`${names(noDryer)}은(는) 건조기를 쓰지 말고 자연건조하세요.`);
  }
  if (washable.some((garment) => fastened.test(text(garment)))) {
    cautions.push('지퍼와 후크는 잠그고 넣어 다른 옷이 걸리지 않게 하세요.');
  }
  if (washable.length > 1) cautions.push('코스별 적정 세탁량을 확인하고, 넘으면 같은 묶음도 나눠서 빨아 주세요.');

  const notes: TogetherPlan['notes'] = [];
  const dryingNotes: TogetherPlan['dryingNotes'] = [];
  for (const garment of garments) {
    const lines: string[] = [];
    if (washable.includes(garment)) {
      if (denim.test(text(garment))) lines.push('뒤집어서 빨면 색 빠짐이 줄어요.');
      else if (printed.test(text(garment))) lines.push('프린트가 상하지 않게 뒤집어서 빨아 주세요.');
      if (isDelicate(garment)) lines.push('세탁망에 넣어 주세요.');
    }
    const drying: string[] = [];
    for (const line of (garment.careNotes ?? '').split('\n').flatMap((part) => part.split(/(?<=[.。])\s+/))) {
      const note = line.trim();
      if (!note || redundantNote.test(note)) continue;
      // 표백·다림질·드라이클리닝이 섞인 줄은 쪼개지 않고 그대로 두므로 건조 안내로 옮기지 않는다.
      const target = dryingNote.test(note) && !mixedNote.test(note) ? drying : lines;
      if (!target.includes(note)) target.push(note);
    }
    if (lines.length) notes.push({ garment, lines: lines.slice(0, 6) });
    if (drying.length) dryingNotes.push({ garment, lines: drying });
  }

  return { apart, pending, conflicts, loads, cautions, notes, dryingNotes };
}

const redundantNote = /세탁기로 세탁(할 수 있|이 가능|가능)|기계\s*세탁(이|은)?\s*(가능|할 수)|최대 세탁 온도/;
const dryingNote = /건조|말리/;
const mixedNote = /표백|다림|드라이/;

function waterAdvice(garments: Garment[]) {
  const limits = garments.filter((garment) => garment.maxTemp !== null);
  if (!limits.length) return '세탁 라벨에서 허용 물 온도를 확인해 주세요.';
  const lowest = limits.reduce((a, b) => (b.maxTemp! < a.maxTemp! ? b : a));
  const missing = limits.length < garments.length ? ' 나머지 옷의 온도 제한도 확인해 주세요.' : '';
  return `물 온도는 ${lowest.maxTemp}°C 이하로 맞추세요(${lowest.name} 기준).${missing}`;
}

export type MachineGuide = {
  course: string; courseLabel: string; courseId: string; setting: VerifiedSetting;
  checks: string[]; assumptions: string[]; sourceUrl: string | null;
};

const strengthRank = { very_gentle: 0, gentle: 1, normal: 2 } as const;
const strongSpin = /^(extra high|high|강|최강|강력)$/i;
const coldName = /\bcold\b|찬물|냉수/i;
const warmName = /warm|따뜻|온수|미지근/i;
const hotName = /hot|뜨거|고온/i;
const lowSpin = /^(no spin|low|약|저|없음)$/i;
const mediumSpin = /^(medium|중|보통)$/i;
const temperatureNameRank = (name: string) => coldName.test(name) ? 0 : hotName.test(name) ? 3 : warmName.test(name) ? 2 : 1;
const spinNameRank = (name: string) => lowSpin.test(name) ? 0 : mediumSpin.test(name) ? 1 : strongSpin.test(name) ? 3 : 2;

function maximumStrength(garments: Garment[]) {
  return Math.min(...garments.map((item) => Math.min(
    strengthRank[item.washStrength ?? 'normal'], isDelicate(item) ? strengthRank.gentle : strengthRank.normal,
  )));
}

function settingStrength(course: Course, setting: VerifiedSetting) {
  return strengthRank[setting.washStrength ?? (course.gentle ? 'gentle' : 'normal')];
}

export function machineGuide(garments: Garment[], machine: Machine): MachineGuide | null {
  if (!garments.length || garments.some(({ wash }) => wash !== 'machine')) return null;

  // 정보가 없으면 가장 안전한 값(약한 세탁, 찬물)으로 고르고 그 사실을 알린다.
  const tempUnknown = garments.some(({ maxTemp }) => maxTemp === null);
  const maxTemp = Math.min(...garments.map((item) => item.maxTemp ?? 30));
  const maxSpin = Math.min(...garments.map((item) => item.maxSpin ?? Infinity));
  const maxStrength = maximumStrength(garments);

  const options = machine.courses.flatMap((course) => (course.verifiedSettings ?? [])
    .filter((setting) => {
      const strength = settingStrength(course, setting);
      return strength <= maxStrength && !setting.dryLevel && setting.spin !== '미확인' && setting.temperature !== '미확인'
        && (setting.temperatureCelsius === null ? !tempUnknown || coldName.test(setting.temperature) : setting.temperatureCelsius <= maxTemp)
        && (setting.spinRpm === null ? (maxStrength === strengthRank.normal || !strongSpin.test(setting.spin)) : setting.spinRpm <= maxSpin);
    })
    .map((setting) => ({ course, setting })));
  const best = options.sort((a, b) =>
    Number(a.setting.temperatureCelsius === null) - Number(b.setting.temperatureCelsius === null)
    || (a.setting.spinRpm ?? Infinity) - (b.setting.spinRpm ?? Infinity)
    || (a.setting.temperatureCelsius === null && b.setting.temperatureCelsius === null
      ? temperatureNameRank(a.setting.temperature) - temperatureNameRank(b.setting.temperature) : 0)
    || spinNameRank(a.setting.spin) - spinNameRank(b.setting.spin)
    || Number(b.setting.isDefault) - Number(a.setting.isDefault))[0];
  if (!best) return null;

  const { course, setting } = best;
  const courseName = course.panelName ?? course.name;
  const checks: string[] = [];
  if (setting.temperatureCelsius === null) {
    checks.push(`「${setting.temperature}」가 실제로 ${maxTemp}°C 이하인지`);
  }
  if (setting.spinRpm === null) {
    checks.push(Number.isFinite(maxSpin)
      ? `「${setting.spin}」이 ${maxSpin} rpm 이하인지`
      : `라벨에 탈수 제한이 있으면 「${setting.spin}」의 회전수`);
  }
  const assumptions: string[] = [];
  if (garments.some(strengthUnknown)) assumptions.push('세탁 강도가 확인되지 않아 약한 세탁 기준으로 골랐어요.');
  if (tempUnknown) assumptions.push('최대 물 온도가 확인되지 않아 찬물 설정만 골랐어요.');
  const courseLabel = course.panelName && course.panelName !== course.name ? `${course.name} (${course.panelName})` : courseName;
  return { course: courseName, courseLabel, courseId: course.id, setting, checks, assumptions, sourceUrl: setting.sourceUrl ?? machine.sourceUrl ?? null };
}

export function checkLoadSetting(garments: Garment[], machine: Machine, courseId: string, temp: number, spin: number): {
  status: 'ok' | 'adjust' | 'unknown'; reasons: string[];
} {
  const course = machine.courses.find(({ id }) => id === courseId);
  if (!course || !Number.isFinite(temp) || !Number.isFinite(spin)) {
    return { status: 'unknown', reasons: ['코스, 세탁 온도, 탈수 속도를 모두 입력해 주세요.'] };
  }
  const reasons: string[] = [];
  const unknownReasons: string[] = [];
  for (const garment of garments) {
    if (garment.wash !== 'machine' || garment.maxTemp === null || (garment.gentle === null && !garment.washStrength)) {
      unknownReasons.push(`${garment.name}의 세탁 가능 여부·온도·강도를 확인해야 비교할 수 있어요.`);
    }
    if (garment.maxTemp !== null && temp > garment.maxTemp) {
      reasons.push(`${garment.name}의 최대 세탁 온도는 ${garment.maxTemp}°C예요.`);
    }
    if (garment.maxSpin != null && spin > garment.maxSpin) {
      reasons.push(`${garment.name}의 최대 탈수 속도는 ${garment.maxSpin}rpm이에요.`);
    }
  }
  const options = course.verifiedSettings?.filter((setting) =>
    setting.temperatureCelsius === temp && setting.spinRpm === spin && !setting.dryLevel) ?? [];
  if (options.length && options.every((setting) => settingStrength(course, setting) > maximumStrength(garments))) {
    reasons.push('선택한 설정의 세탁 강도가 이 묶음의 허용 범위를 넘어가요.');
  }
  if (reasons.length) return { status: 'adjust', reasons };
  if (unknownReasons.length) return { status: 'unknown', reasons: unknownReasons };
  if (!options.length) {
    return { status: 'unknown', reasons: ['이 코스의 해당 온도·탈수 조합은 설명서에서 확인되지 않았어요.'] };
  }
  return { status: 'ok', reasons: ['확인된 코스 설정이 이 묶음의 세탁 조건을 충족해요.'] };
}
