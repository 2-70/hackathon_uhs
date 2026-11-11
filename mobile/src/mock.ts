import type { Course, Garment, GarmentDraft, Machine, Plan } from './model';

export const blankGarment: GarmentDraft = {
  name: '',
  category: '',
  color: '',
  material: '',
  wash: 'unknown',
  maxTemp: null,
  gentle: false,
  dryer: 'unknown',
  drying: '',
  source: 'manual',
};

export const sampleGarments: Garment[] = [
  {
    ...blankGarment,
    id: 'sample-tee',
    name: '흰 면 티셔츠',
    category: '티셔츠',
    color: '흰색',
    material: '면 100%',
    wash: 'machine',
    maxTemp: 40,
    dryer: 'yes',
    drying: '낮은 온도로 건조하거나 걸어서 말리세요.',
    source: 'sample-product',
  },
  {
    ...blankGarment,
    id: 'sample-shirt',
    name: '크림색 셔츠',
    category: '셔츠',
    color: '크림색',
    material: '면 80%, 리넨 20%',
    wash: 'machine',
    maxTemp: 30,
    gentle: true,
    dryer: 'no',
    drying: '모양을 잡아 그늘에 걸어서 말리세요.',
    source: 'sample-label',
  },
  {
    ...blankGarment,
    id: 'sample-jeans',
    name: '검은 데님 팬츠',
    category: '바지',
    color: '검정',
    material: '면 98%, 폴리우레탄 2%',
    wash: 'machine',
    maxTemp: 30,
    dryer: 'no',
    drying: '뒤집어서 그늘에 걸어 말리세요.',
    source: 'sample-label',
  },
  {
    ...blankGarment,
    id: 'sample-knit',
    name: '베이지 울 니트',
    category: '니트',
    color: '베이지',
    material: '울 100%',
    wash: 'hand',
    maxTemp: 30,
    gentle: true,
    dryer: 'no',
    drying: '수건 위에 펼쳐 그늘에서 말리세요.',
    source: 'sample-label',
  },
  {
    ...blankGarment,
    id: 'sample-jacket',
    name: '초록색 재킷',
    category: '아우터',
    color: '초록색',
  },
];

export const sampleMachines: Machine[] = [
  {
    id: 'sample-machine-a',
    maker: '워시와이즈 샘플',
    model: 'WW-DEMO 100',
    courses: [
      {
        id: 'standard',
        name: '표준',
        gentle: false,
        settings: [
          { temp: 20, spin: 800 },
          { temp: 30, spin: 800 },
          { temp: 40, spin: 1000 },
        ],
      },
      {
        id: 'gentle',
        name: '섬세',
        gentle: true,
        settings: [
          { temp: 20, spin: 400 },
          { temp: 30, spin: 600 },
        ],
      },
    ],
  },
  {
    id: 'sample-machine-b',
    maker: '워시와이즈 샘플',
    model: 'WW-DEMO 200',
    courses: [
      {
        id: 'standard',
        name: '혼합',
        gentle: false,
        settings: [
          { temp: 30, spin: 700 },
          { temp: 40, spin: 900 },
        ],
      },
      {
        id: 'gentle',
        name: '약한 세탁',
        gentle: true,
        settings: [{ temp: 20, spin: 400 }],
      },
    ],
  },
];

export async function searchMachines(query: string): Promise<Machine[]> {
  const terms = query.toLowerCase().trim().split(/\s+/);
  return sampleMachines.filter(({ maker, model }) => {
    const name = `${maker} ${model}`.toLowerCase();
    return terms.every((term) => name.includes(term));
  });
}

export async function analyzePhoto(kind: 'clothing' | 'label', uri: string): Promise<{
  status: 'exact' | 'candidate' | 'not-found' | 'label';
  care: Partial<GarmentDraft>;
  source?: string;
  pending: string[];
}> {
  if (!uri.trim()) {
    throw new Error('사진을 다시 선택해 주세요.');
  }

  if (kind === 'label') {
    return {
      status: 'label',
      care: {
        material: '면 100%',
        wash: 'machine',
        maxTemp: 30,
        gentle: true,
        dryer: 'no',
        drying: '그늘에 걸어서 말리세요.',
        source: 'sample-label',
      },
      source: '샘플 라벨 응답',
      pending: ['라벨과 예시 값이 일치하는지 확인해 주세요.'],
    };
  }

  return {
    status: 'candidate',
    care: {},
    source: '샘플 상품 검색 응답',
    pending: ['제품 식별 정보', '소재와 혼용률', '세탁 및 건조 조건'],
  };
}

type Setting = Course['settings'][number] & { course: Course };
type ColorFamily = 'light' | 'dark' | 'unknown';

function colorFamily(color: string): ColorFamily {
  const normalized = color.trim().toLowerCase();
  if (/^(흰|흰색|하양|하얀색|화이트|크림|크림색|아이보리|베이지|white|cream|ivory|beige)$/.test(normalized)) {
    return 'light';
  }
  if (/^(검정|검정색|검은색|블랙|네이비|진청|남색|black|navy)$/.test(normalized)) {
    return 'dark';
  }
  return 'unknown';
}

function getExclusionReason(garment: Garment): string | undefined {
  if (garment.wash === 'none') return '물세탁 금지 의류예요.';
  if (garment.wash === 'hand') return '손세탁이 필요한 의류예요.';
  if (garment.wash === 'unknown') return '기계세탁 가능 여부를 확인해 주세요.';
  if (garment.maxTemp === null) return '최대 세탁 온도를 확인해 주세요.';
  return undefined;
}

function isCompatible(garment: Garment, setting: Setting): boolean {
  return (
    garment.maxTemp !== null &&
    setting.temp <= garment.maxTemp &&
    (!garment.gentle || setting.course.gentle)
  );
}

export async function calculatePlan(garments: Garment[], machine: Machine): Promise<Plan> {
  if (garments.length > 10) {
    throw new Error('한 번에 의류를 최대 10벌까지 분석할 수 있어요.');
  }

  const settings = machine.courses.flatMap((course) =>
    course.settings.map((setting) => ({ ...setting, course })),
  );
  const excluded: Plan['excluded'] = [];
  const groups: { family: ColorFamily; garments: Garment[]; options: Setting[] }[] = [];

  for (const garment of garments) {
    const exclusion = getExclusionReason(garment);
    if (exclusion) {
      excluded.push({ garment, reason: exclusion });
      continue;
    }

    const options = settings.filter((setting) => isCompatible(garment, setting));
    if (options.length === 0) {
      excluded.push({ garment, reason: '이 기기에서 의류 조건에 맞는 설정을 찾지 못했어요.' });
      continue;
    }

    const family = colorFamily(garment.color);
    const group = groups.find(
      (entry) =>
        family !== 'unknown' &&
        family === entry.family &&
        entry.options.some((option) => options.includes(option)),
    );

    if (group) {
      group.garments.push(garment);
      group.options = group.options.filter((option) => options.includes(option));
    } else {
      groups.push({ family, garments: [garment], options });
    }
  }

  return {
    groups: groups.map(({ family, garments: items, options }) => {
      const { course, temp, spin } = options.find((option) => option.temp === 30) ?? options[0];
      const reason = {
        light: '밝은색 의류끼리 모아 공통으로 사용할 수 있는 설정을 골랐어요.',
        dark: '이염을 줄이도록 어두운색 의류를 밝은색 의류와 분리했어요.',
        unknown: '이염 여부를 확인하기 어려운 색상은 따로 분리했어요.',
      }[family];

      return {
        id: JSON.stringify(items.map(({ id }) => id).sort()),
        garments: items,
        course,
        temp,
        spin,
        reason,
      };
    }),
    excluded,
  };
}

export async function validateSettings(
  group: Plan['groups'][number],
  machine: Machine,
  courseId: string,
  temp: number,
  spin: number,
): Promise<{ status: 'ok' | 'adjust' | 'unknown'; reasons: string[] }> {
  const course = machine.courses.find(({ id }) => id === courseId);
  if (
    !course ||
    !Number.isFinite(temp) ||
    !Number.isFinite(spin) ||
    group.garments.length === 0 ||
    group.garments.some((garment) => getExclusionReason(garment))
  ) {
    return { status: 'unknown', reasons: ['코스, 세탁 온도, 탈수 속도를 모두 확인해 주세요.'] };
  }

  const reasons = [];
  if (!course.settings.some((option) => option.temp === temp && option.spin === spin)) {
    reasons.push('이 코스에서 온도와 탈수 속도를 함께 선택할 수 없어요.');
  }
  for (const garment of group.garments) {
    if (garment.maxTemp !== null && temp > garment.maxTemp) {
      reasons.push(`${garment.name}의 최대 세탁 온도는 ${garment.maxTemp}°C예요.`);
    }
    if (garment.gentle && !course.gentle) {
      reasons.push(`${garment.name}에는 약한 세탁 코스가 필요해요.`);
    }
  }

  if (reasons.length) return { status: 'adjust', reasons };
  return { status: 'ok', reasons: ['기기 지원 설정과 의류 관리 조건을 모두 충족해요.'] };
}
