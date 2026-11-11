import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseMaterialGuidance, toAnalysis } from './analysis.ts';

type PhotoResponse = Parameters<typeof toAnalysis>[0];

test('material guidance separates a labeled estimate from its instruction and keeps old tips plain', () => {
  assert.deepEqual(parseMaterialGuidance('물 온도 · 찬물 또는 30℃ 이하로 세탁하세요.'), {
    label: '물 온도',
    instruction: '찬물 또는 30℃ 이하로 세탁하세요.',
  });
  assert.equal(parseMaterialGuidance('세탁망에 넣어 세탁하세요.'), null);
});

function matchedProductResponse(overrides: Partial<PhotoResponse> = {}) {
  const base: PhotoResponse = {
    image_type: 'garment',
    garment: {},
    care_label: {},
    product_care: {},
    product_lookup: {
      status: 'matched',
      product: {
        name: '에어리 셔츠',
        source_url: 'https://example.com/product',
        product_code: 'ABC-123',
      },
    },
    care_guidance: [],
    care_guidance_source: null,
    photo_request: { image_type: 'care_label', instructions: '세탁 라벨을 추가해 주세요.' },
    message: '같은 상품을 찾았어요.',
  };
  return toAnalysis({ ...base, ...overrides });
}

test('published product care stays separate from provisional material guidance', () => {
  const result = matchedProductResponse({
    product_care: {
      wash_method: { value: 'machine_wash', status: 'verified', source: 'product_listing' },
      fiber_content: { value: '면 70%, 폴리에스터 30%', status: 'verified', source: 'product_listing' },
    },
    care_guidance: [
      '세탁기로 세탁할 수 있어요.',
      '소재 기준 권장: 세탁망에 넣어 세탁하세요.',
    ],
    care_guidance_source: 'product_listing',
  });

  assert.equal(result.hasPublishedCare, true);
  assert.equal(result.care.wash, 'machine');
  assert.deepEqual(result.guidance, ['세탁기로 세탁할 수 있어요.']);
  assert.deepEqual(result.materialGuidance, ['세탁망에 넣어 세탁하세요.']);
  assert.equal(result.care.careNotes, '세탁기로 세탁할 수 있어요.');
  assert.equal(result.followUp, 'label');
});

test('material estimate never becomes a confirmed wash rule or care note', () => {
  const result = matchedProductResponse({
    product_care: {
      fiber_content: { value: '울 40%, 면 60%', status: 'verified', source: 'product_listing' },
      wash_method: { value: null, status: 'needs_confirmation', source: 'product_listing' },
    },
    care_guidance: [
      '소재 기준 권장: 라벨에서 물세탁을 허용하면 세탁망을 사용하세요.',
      '소재 기준 권장: 평평하게 펴서 말리세요.',
    ],
    care_guidance_source: 'material_estimate',
  });

  assert.equal(result.hasPublishedCare, false);
  assert.equal(result.care.wash, undefined);
  assert.equal(result.care.maxTemp, undefined);
  assert.equal(result.care.careNotes, undefined);
  assert.deepEqual(result.guidance, []);
  assert.deepEqual(result.materialGuidance, [
    '라벨에서 물세탁을 허용하면 세탁망을 사용하세요.',
    '평평하게 펴서 말리세요.',
  ]);
  assert.equal(result.followUp, 'label');
});

test('generic fallback tips are suppressed for an exact product with no published care', () => {
  const result = matchedProductResponse({
    care_guidance: ['비슷한 색끼리 세탁하세요.'],
    care_guidance_source: 'estimated',
  });

  assert.equal(result.status, 'exact');
  assert.equal(result.hasPublishedCare, false);
  assert.equal(result.estimated, false);
  assert.deepEqual(result.guidance, []);
  assert.equal(result.followUp, 'label');
});
