import assert from 'node:assert/strict';
import { test } from 'node:test';
import { blankGarment } from './mock.ts';
import type { Garment, Machine, VerifiedSetting } from './model.ts';
import { checkLoadSetting, colorFamily, machineGuide, planTogether } from './together.ts';

function garment(id: string, values: Partial<Garment>): Garment {
  return { ...blankGarment, id, name: id, wash: 'machine', maxTemp: 40, gentle: false, ...values };
}

test('colors are sorted by dye transfer risk', () => {
  assert.equal(colorFamily('흰색'), 'light');
  assert.equal(colorFamily('연한 파랑'), 'light');
  assert.equal(colorFamily('진청'), 'deep');
  assert.equal(colorFamily('초록색'), 'deep');
  assert.equal(colorFamily(''), 'unknown');
});

test('multi-colour values are deep if any part is deep, else light if any part is light', () => {
  assert.equal(colorFamily('미디엄 애쉬/블랙/화이트'), 'deep');
  assert.equal(colorFamily('흰색, 아이보리'), 'light');
  assert.equal(colorFamily('화이트 · 모를색'), 'light');
  assert.equal(colorFamily('모를색/이름없음'), 'unknown');
  assert.equal(colorFamily('연한 파랑 & 흰색'), 'light');
});

test('care notes are split into lines, drop restated facts, and route drying lines separately', () => {
  const plan = planTogether([garment('셔츠', {
    color: '흰색',
    careNotes: '세탁기로 세탁할 수 있어요. 최대 세탁 온도는 30°C예요.\n중성세제를 쓰세요. 중성세제를 쓰세요. 건조기를 쓰지 마세요.\n그늘에서 말리세요.',
  })]);
  assert.deepEqual(plan.notes[0].lines, ['중성세제를 쓰세요.']);
  assert.deepEqual(plan.dryingNotes[0].lines, ['건조기를 쓰지 마세요.', '그늘에서 말리세요.']);
  const blob = '염소 및 산소계 표백제로 표백할 수 없음 150°C 정도로 다림질 가능 (천 대고 다림질) 드라이클리닝 금지 세탁 후 즉시 건조, 비슷한 색상끼리 세탁';
  const mixed = planTogether([garment('블라우스', { careNotes: blob })]);
  assert.deepEqual(mixed.notes[0].lines, [blob]);
  assert.equal(mixed.dryingNotes.length, 0);
  const many = planTogether([garment('긴 메모', { careNotes: ['가', '나', '다', '라', '마', '바', '사'].map((x) => x + '를 하세요.').join(' ') })]);
  assert.equal(many.notes[0].lines.length, 6);
});

test('a conditional machine guide is not reported as not found', () => {
  const machine: Machine = {
    ...levelMachine,
    courses: [{ ...levelMachine.courses[0], verifiedSettings: [setting('warm-medium', 'Warm', 'Medium')] }],
  };
  const conditional = garment('블라우스', { gentle: true, maxTemp: 30, color: '흰색' });
  const missing = garment('티셔츠', { washStrength: 'very_gentle', maxTemp: 30, color: '흰색' });
  assert.ok(machineGuide([conditional], machine)!.checks.length > 0);
  assert.equal(machineGuide([missing], machine), null);

  const single = planTogether([conditional], machine);
  assert.equal(single.loads.length, 1);
  assert.match(single.loads[0].label, / · 확인 후 사용$/);
  assert.doesNotMatch(single.loads[0].label, /설정 확인 필요/);
  assert.doesNotMatch(single.loads[0].advice, /찾지 못했어요/);

  const both = planTogether([conditional, missing], machine);
  const byFirst = (name: string) => both.loads.find(({ garments }) => garments[0].name === name)!;
  assert.match(byFirst('블라우스').label, /확인 후 사용/);
  assert.doesNotMatch(byFirst('블라우스').advice, /찾지 못했어요/);
  assert.match(byFirst('티셔츠').label, /설정 확인 필요/);
  assert.match(byFirst('티셔츠').advice, /찾지 못했어요/);
});

test('garments that cannot go in the machine are set apart with the reason', () => {
  const plan = planTogether([
    garment('코트', { wash: 'none' }),
    garment('니트', { wash: 'hand', material: '울 100%' }),
    garment('가죽 재킷', { material: '소가죽' }),
    garment('티셔츠', { color: '흰색' }),
  ]);
  assert.deepEqual(plan.apart.map(({ garment: item }) => item.name), ['코트', '니트', '가죽 재킷']);
  assert.match(plan.apart[0].reason, /물세탁 금지/);
  assert.match(plan.apart[1].reason, /손세탁/);
  assert.deepEqual(plan.loads.map(({ garments }) => garments.map(({ name }) => name)), [['티셔츠']]);
});

test('light and deep colors are split and the conflict is explained', () => {
  const plan = planTogether([
    garment('흰 티셔츠', { color: '흰색' }),
    garment('검은 청바지', { color: '검정', category: '바지', material: '데님', maxTemp: 30 }),
  ]);
  assert.equal(plan.conflicts.length, 1);
  assert.match(plan.conflicts[0].reason, /물이 들/);
  assert.deepEqual(plan.loads.map(({ label }) => label), ['밝은색', '진한색']);
  assert.match(plan.loads[1].advice, /30°C 이하/);
  assert.deepEqual(plan.notes.map(({ garment: item, lines }) => [item.name, lines[0]]), [
    ['검은 청바지', '뒤집어서 빨면 색 빠짐이 줄어요.'],
  ]);
});

test('one compatible load gets shared cautions for temperature, course and dryer', () => {
  const plan = planTogether([
    garment('흰 티셔츠', { color: '흰색', dryer: 'yes' }),
    garment('크림 블라우스', { color: '크림', gentle: true, maxTemp: 30, dryer: 'no', careNotes: '중성세제를 쓰세요.' }),
  ]);
  assert.equal(plan.conflicts.length, 0);
  assert.equal(plan.loads.length, 1);
  assert.ok(plan.cautions.some((line) => /30°C 이하/.test(line) && line.includes('크림 블라우스')));
  assert.ok(plan.cautions.some((line) => line.includes('섬세 코스')));
  assert.ok(plan.cautions.some((line) => line.startsWith('건조기에는 흰 티셔츠만')));
  assert.deepEqual(plan.notes[0].lines, ['세탁망에 넣어 주세요.', '중성세제를 쓰세요.']);
});

test('delicate fabric is kept away from denim of the same color', () => {
  const plan = planTogether([
    garment('네이비 니트', { color: '네이비', category: '니트', material: '면 100%' }),
    garment('진청 데님', { color: '진청', material: '데님' }),
  ]);
  assert.ok(plan.conflicts.some(({ reason }) => /쓸려/.test(reason)));
  assert.deepEqual(plan.loads.map(({ label }) => label), ['진한색 · 약한 세탁', '진한색']);
});

test('split advice is reflected in the loads and only an unknown wash method is held for confirmation', () => {
  const items = [
    garment('검은 수건', { color: '검정' }),
    garment('검은 티셔츠', { color: '검정' }),
    garment('단독 세탁 바지', { color: '검정', washSeparately: true }),
    garment('색 미등록', {}),
    garment('색 미등록 2', {}),
    garment('라벨 미등록', { wash: 'unknown' }),
    garment('온도 미등록', { maxTemp: null }),
    garment('강도 미등록', { gentle: null }),
  ];
  const plan = planTogether(items);
  assert.equal(plan.loads.length, 7);
  assert.deepEqual(plan.pending.map(({ garment: item }) => item.id), ['라벨 미등록']);
  assert.ok(plan.conflicts.some(({ reason }) => reason.includes('보풀')));
  for (const { first, second } of plan.conflicts) {
    assert.ok(!plan.loads.some(({ garments }) => first.some((item) => garments.includes(item))
      && second.some((item) => garments.includes(item))));
  }
  assert.deepEqual(plan.loads.flatMap(({ garments }) => garments.map(({ id }) => id)),
    items.filter(({ id }) => id !== '라벨 미등록').map(({ id }) => id));
  const strengthLoad = plan.loads.find(({ garments }) => garments[0].id === '강도 미등록')!;
  assert.match(strengthLoad.label, /약한 세탁/);
  assert.match(strengthLoad.advice, /라벨에서 확인/);
  assert.match(plan.loads.find(({ garments }) => garments[0].id === '온도 미등록')!.advice, /허용 물 온도를 확인/);
});

function setting(id: string, temperature: string, spin: string, values: Partial<VerifiedSetting> = {}): VerifiedSetting {
  return {
    id, temperature, spin, temperatureCelsius: null, spinRpm: null, washStrength: null,
    waterLevel: null, dryLevel: null, isDefault: true, sourceUrl: null, manualPage: null, ...values,
  };
}

const levelMachine: Machine = {
  id: 'm', maker: 'LG', model: 'WM4000HWA',
  courses: [
    { id: 'd', name: '섬세', panelName: 'Delicates', gentle: true, settings: [], verifiedSettings: [setting('1', 'Cold', 'Medium')] },
    { id: 'n', name: '표준', gentle: false, settings: [], verifiedSettings: [setting('2', 'Warm', 'High')] },
    { id: 's', name: '급속', gentle: false, settings: [], verifiedSettings: [setting('3', 'Hot', 'Extra High')] },
  ],
};

test('the machine guide shows confirmed panel labels and asks for missing numeric values', () => {
  const soft = machineGuide([garment('블라우스', { gentle: true, maxTemp: 30, maxSpin: 600 })], levelMachine)!;
  assert.equal(soft.course, 'Delicates');
  assert.equal(soft.courseLabel, '섬세 (Delicates)');
  assert.equal(soft.setting.temperature, 'Cold');
  assert.equal(soft.setting.spin, 'Medium');
  assert.deepEqual(soft.checks, ['「Cold」가 실제로 30°C 이하인지', '「Medium」이 600 rpm 이하인지']);
  assert.deepEqual(machineGuide([garment('셔츠', { gentle: true, maxTemp: 30 })], levelMachine)!.checks[1],
    '라벨에 탈수 제한이 있으면 「Medium」의 회전수');
  const needsTemperatureCheck = machineGuide([garment('티셔츠', { maxTemp: 40 })], { ...levelMachine, courses: levelMachine.courses.slice(1) });
  assert.ok(needsTemperatureCheck?.checks.some((line) => line.includes('실제로 40°C 이하')));
  assert.equal(machineGuide([garment('티셔츠', {})], { ...levelMachine, courses: [] }), null);
});

test('a garment with unknown strength gets the gentlest course and says what was assumed', () => {
  const item = garment('라벨 셔츠', { maxTemp: 30, gentle: null, washStrength: null });
  const guide = machineGuide([item], levelMachine)!;
  assert.equal(guide.courseId, 'd');
  assert.equal(guide.setting.temperature, 'Cold');
  assert.ok(guide.checks.some((line) => line.includes('30°C 이하')));
  assert.deepEqual(guide.assumptions, ['세탁 강도가 확인되지 않아 약한 세탁 기준으로 골랐어요.']);
  assert.equal(machineGuide([garment('일반', {})], levelMachine)!.assumptions.length, 0);
  const plan = planTogether([item], levelMachine);
  assert.equal(plan.pending.length, 0);
  assert.match(plan.loads[0].label, /약한 세탁/);
  assert.equal(checkLoadSetting([item], levelMachine, 'd', 30, 600).status, 'unknown');
});

test('a garment with unknown max temperature only gets a cold setting', () => {
  const item = garment('온도 모름', { maxTemp: null, gentle: true });
  const guide = machineGuide([item], levelMachine)!;
  assert.equal(guide.setting.temperature, 'Cold');
  assert.deepEqual(guide.assumptions, ['최대 물 온도가 확인되지 않아 찬물 설정만 골랐어요.']);
  const warmOnly = { ...levelMachine, courses: levelMachine.courses.slice(1) };
  assert.equal(machineGuide([{ ...item, gentle: false }], warmOnly), null);
  const numeric = { ...levelMachine, courses: [{ ...levelMachine.courses[0], verifiedSettings: [
    setting('40', '40°C', 'Low', { temperatureCelsius: 40, spinRpm: 400 }),
    setting('20', '20°C', 'Low', { temperatureCelsius: 20, spinRpm: 400 }),
  ] }] };
  assert.equal(machineGuide([item], numeric)?.setting.id, '20');
});

test('unnamed-temperature ties prefer colder, then gentler spin names', () => {
  const machine: Machine = { ...levelMachine, courses: [{ ...levelMachine.courses[0], verifiedSettings: [
    setting('warm', 'Warm', 'Low'), setting('cold-high', 'Cold', 'High'), setting('cold-low', 'Cold', 'Low'),
  ] }] };
  assert.equal(machineGuide([garment('티', { gentle: true, maxTemp: 40 })], machine)?.setting.id, 'cold-low');
});

test('the machine-aware plan uses model settings and keeps unknown numeric values confirmation-required', () => {
  const machine: Machine = {
    ...levelMachine,
    courses: [{ ...levelMachine.courses[0], verifiedSettings: [setting('warm-medium', 'Warm', 'Medium')] }],
  };
  const item = garment('라벨 블라우스', { gentle: true, maxTemp: 30, maxSpin: 600 });
  const guide = machineGuide([item], machine);
  assert.ok(guide);
  assert.equal(guide.setting.temperature, 'Warm');
  assert.ok(guide.checks.some((line) => line.includes('실제로 30°C 이하')));
  assert.ok(guide.checks.some((line) => line.includes('600 rpm 이하')));

  const plan = planTogether([item], machine);
  assert.equal(plan.loads.length, 1);
  assert.equal(machineGuide(plan.loads[0].garments, machine)?.setting.id, 'warm-medium');
  assert.equal(planTogether([item]).loads[0].label, '색상 미확인 · 단독 세탁 · 약한 세탁');
});

test('the same garment gets model-specific settings and unknown placeholders are never suggested', () => {
  const item = garment('셔츠', { gentle: true, maxTemp: 30, maxSpin: 600 });
  const modelA: Machine = {
    ...levelMachine,
    courses: [{ id: 'a', name: 'A 섬세', panelName: 'A Delicate', gentle: true, settings: [], verifiedSettings: [setting('a-setting', '30°C', '600 rpm', { temperatureCelsius: 30, spinRpm: 600 })] }],
  };
  const modelB: Machine = {
    ...levelMachine,
    id: 'm2', model: 'WM-B',
    courses: [{ id: 'b', name: 'B 섬세', panelName: 'B Gentle', gentle: true, settings: [], verifiedSettings: [setting('b-setting', 'Cold', 'Low', { temperatureCelsius: 30, spinRpm: 400 })] }],
  };
  assert.equal(machineGuide([item], modelA)?.setting.id, 'a-setting');
  assert.equal(machineGuide([item], modelB)?.setting.id, 'b-setting');
  const unknown = { ...modelA, courses: [{ ...modelA.courses[0], verifiedSettings: [setting('unknown', '미확인', '600 rpm', { temperatureCelsius: null, spinRpm: 600 })] }] };
  assert.equal(machineGuide([item], unknown), null);
});

test('the selected model separates a shared load when only individual setting combinations fit', () => {
  const machine: Machine = {
    ...levelMachine,
    courses: [
      { id: 'cool-high', name: 'Cool high', gentle: false, settings: [], verifiedSettings: [setting('cool-high', '30°C', '1400 rpm', { temperatureCelsius: 30, spinRpm: 1400 })] },
      { id: 'warm-low', name: 'Warm low', gentle: false, settings: [], verifiedSettings: [setting('warm-low', '40°C', '600 rpm', { temperatureCelsius: 40, spinRpm: 600 })] },
    ],
  };
  const plan = planTogether([
    garment('셔츠', { color: '검정', maxTemp: 30, maxSpin: 1400 }),
    garment('바지', { color: '검정', maxTemp: 40, maxSpin: 600 }),
  ], machine);
  assert.equal(plan.loads.length, 2);
  assert.deepEqual(plan.loads.map(({ garments }) => garments[0].name), ['셔츠', '바지']);
  assert.deepEqual(plan.loads.map(({ garments }) => machineGuide(garments, machine)?.setting.id), ['cool-high', 'warm-low']);
  assert.match(plan.loads[0].advice, /1400rpm 이하/);
  assert.match(plan.loads[1].advice, /600rpm 이하/);
});

test('a lower confirmed combination wins when the default exceeds a garment limit', () => {
  const machine: Machine = {
    ...levelMachine,
    courses: [{ ...levelMachine.courses[0], verifiedSettings: [
      setting('default', '40°C', '1000 rpm', { temperatureCelsius: 40, spinRpm: 1000 }),
      setting('cooler', '30°C', '600 rpm', { temperatureCelsius: 30, spinRpm: 600, isDefault: false }),
    ] }],
  };
  const item = garment('블라우스', { gentle: true, maxTemp: 30, maxSpin: 700 });
  const guide = machineGuide([item], machine)!;
  assert.equal(guide.checks.length, 0);
  assert.equal(guide.setting.temperature, '30°C');
  assert.equal(guide.setting.spin, '600 rpm');
  assert.equal(machineGuide([{ ...item, wash: 'unknown' }], machine), null);
  assert.equal(machineGuide([{ ...item, maxSpin: 500 }], machine), null);
  assert.equal(machineGuide([{ ...item, washStrength: 'very_gentle' }], machine), null);
  assert.equal(checkLoadSetting([item], machine, 'd', 30, 600).status, 'ok');
  assert.equal(checkLoadSetting([item], machine, 'd', 40, 1000).status, 'adjust');
  assert.equal(checkLoadSetting([item], machine, 'd', 25, 600).status, 'unknown');
  assert.equal(checkLoadSetting([{ ...item, maxTemp: null }], machine, 'd', 30, 600).status, 'unknown');
});
