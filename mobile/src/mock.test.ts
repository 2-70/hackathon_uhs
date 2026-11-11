import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  analyzePhoto,
  calculatePlan,
  sampleGarments,
  sampleMachines,
  searchMachines,
  validateSettings,
} from './mock.ts';

test('sample clothing analysis never assigns care from a candidate', async () => {
  const candidate = await analyzePhoto('clothing', 'file:///sample-garment.jpg');
  assert.equal(candidate.status, 'candidate');
  assert.deepEqual(candidate.care, {});
  assert.ok(candidate.pending.length > 0);
  assert.equal((await analyzePhoto('label', 'file:///sample-label.jpg')).care.source, 'sample-label');
  await assert.rejects(analyzePhoto('clothing', ''));
});

test('machine search matches model words and leaves unmatched queries empty', async () => {
  assert.deepEqual(await searchMachines('demo 200'), [sampleMachines[1]]);
  assert.deepEqual(await searchMachines('미등록 모델'), []);
});

test('sample plan assigns each garment once and uses valid course setting pairs', async () => {
  const plan = await calculatePlan(sampleGarments, sampleMachines[0]);
  assert.deepEqual(plan.groups.map(({ garments }) => garments.map(({ id }) => id)), [
    ['sample-tee', 'sample-shirt'],
    ['sample-jeans'],
  ]);
  assert.deepEqual(plan.excluded.map(({ garment }) => garment.id), ['sample-knit', 'sample-jacket']);
  for (const { course, temp, spin } of plan.groups) {
    assert.ok(course.settings.some((setting) => setting.temp === temp && setting.spin === spin));
  }
  await assert.rejects(calculatePlan(Array(11).fill(sampleGarments[0]), sampleMachines[0]));
});

test('settings validation accepts a valid alternative and reports conflicts', async () => {
  const machine = sampleMachines[0];
  const { groups: [group] } = await calculatePlan(sampleGarments, machine);
  assert.equal((await validateSettings(group, machine, 'gentle', 20, 400)).status, 'ok');

  const unsupportedPair = await validateSettings(group, machine, 'gentle', 30, 400);
  assert.equal(unsupportedPair.status, 'adjust');
  assert.ok(unsupportedPair.reasons.some((reason) => reason.includes('함께 선택')));

  const tooHot = await validateSettings(group, machine, 'standard', 40, 1000);
  assert.equal(tooHot.status, 'adjust');
  assert.ok(tooHot.reasons.some((reason) => reason.includes('30°C')));
  assert.ok(tooHot.reasons.some((reason) => reason.includes('약한 세탁')));
  assert.equal((await validateSettings(group, machine, '', 30, 400)).status, 'unknown');
});

test('a known wash temperature does not imply that a normal cycle is allowed', async () => {
  const garment = { ...sampleGarments[0], gentle: null };
  const plan = await calculatePlan([garment], sampleMachines[0]);
  assert.deepEqual(plan.groups, []);
  assert.deepEqual(plan.excluded, [{ garment, reason: '약한 세탁이 필요한지 확인해 주세요.' }]);
});
