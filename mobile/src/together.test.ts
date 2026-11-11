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

test('split advice is reflected in the loads and missing care is held for confirmation', () => {
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
  assert.equal(plan.loads.length, 5);
  assert.deepEqual(plan.pending.map(({ garment: item }) => item.id), items.slice(5).map(({ id }) => id));
  assert.ok(plan.conflicts.some(({ reason }) => reason.includes('보풀')));
  for (const { first, second } of plan.conflicts) {
    assert.ok(!plan.loads.some(({ garments }) => first.some((item) => garments.includes(item))
      && second.some((item) => garments.includes(item))));
  }
  assert.deepEqual(plan.loads.flatMap(({ garments }) => garments.map(({ id }) => id)), items.slice(0, 5).map(({ id }) => id));
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
  assert.ok(soft.steps.some((line) => line.includes('Cold')));
  assert.ok(soft.steps.some((line) => line.includes('Medium')));
  assert.ok(soft.checks.some((line) => line.includes('30°C 이하')));
  assert.ok(soft.checks.some((line) => line.includes('600 rpm 이하')));
  assert.equal(machineGuide([garment('티셔츠', { maxTemp: 40 })], { ...levelMachine, courses: levelMachine.courses.slice(1) }), null);
  assert.equal(machineGuide([garment('티셔츠', {})], { ...levelMachine, courses: [] }), null);
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
  assert.ok(guide.steps.some((line) => line.includes('30°C')));
  assert.ok(guide.steps.some((line) => line.includes('600 rpm')));
  assert.equal(machineGuide([{ ...item, wash: 'unknown' }], machine), null);
  assert.equal(machineGuide([{ ...item, maxSpin: 500 }], machine), null);
  assert.equal(machineGuide([{ ...item, washStrength: 'very_gentle' }], machine), null);
  assert.equal(checkLoadSetting([item], machine, 'd', 30, 600).status, 'ok');
  assert.equal(checkLoadSetting([item], machine, 'd', 40, 1000).status, 'adjust');
  assert.equal(checkLoadSetting([item], machine, 'd', 25, 600).status, 'unknown');
});
