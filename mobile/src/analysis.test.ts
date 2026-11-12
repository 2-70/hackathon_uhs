import assert from 'node:assert/strict';
import { test } from 'node:test';
import { careSummary, messageWithoutFollowUp, parseMaterialGuidance, splitGuidance, toAnalysis } from './analysis.ts';

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

test('careSummary lists only the values that were read', () => {
  assert.deepEqual(careSummary({}), []);
  assert.deepEqual(careSummary({ wash: 'unknown', dryer: 'unknown' }), []);
  assert.deepEqual(
    careSummary({ wash: 'hand', maxTemp: 30, washStrength: 'very_gentle', dryer: 'no', drying: '평평하게 펴서 말리기' }),
    [
      { label: '세탁 방법', value: '손세탁' },
      { label: '최대 온도', value: '30°C' },
      { label: '세탁 강도', value: '매우 약하게' },
      { label: '건조기', value: '사용 금지' },
      { label: '자연건조', value: '평평하게 펴서 말리기' },
    ],
  );
  assert.deepEqual(careSummary({ wash: 'machine', gentle: false, dryer: 'yes' }).map((c) => c.value), ['기계 세탁', '일반', '사용 가능']);
});

test('splitGuidance splits sentences but leaves unpunctuated text alone', () => {
  assert.deepEqual(
    splitGuidance(['손세탁하세요. 평평하게 펴서 말리세요.', '표백할 수 없음 드라이클리닝 할 수 없음']),
    ['손세탁하세요.', '평평하게 펴서 말리세요.', '표백할 수 없음 드라이클리닝 할 수 없음'],
  );
});

test('messageWithoutFollowUp strips the appended follow-up instructions once', () => {
  const result = matchedProductResponse({ message: '라벨을 읽지 못했어요.' });
  assert.equal(result.message, '라벨을 읽지 못했어요. 세탁 라벨을 추가해 주세요.');
  assert.equal(messageWithoutFollowUp(result.message, result.followUpInstructions), '라벨을 읽지 못했어요.');
  assert.equal(messageWithoutFollowUp('안내만 있어요.', undefined), '안내만 있어요.');
});

function labelResponse(overrides: Partial<PhotoResponse> = {}) {
  return toAnalysis({
    image_type: 'care_label',
    garment: {},
    care_label: {},
    product_care: {},
    product_lookup: null,
    care_guidance: [],
    care_guidance_source: null,
    photo_request: null,
    message: '라벨에서 읽었어요.',
    ...overrides,
  });
}

test('a worded water reading from the label is shown as 물 온도 and kept in saved guidance', () => {
  const result = labelResponse({
    care_label: {
      wash_method: { value: 'hand_wash', status: 'read_from_label', source: 'care_label' },
      wash_water: { value: '찬물로 세탁하세요.', status: 'read_from_label', source: 'care_label' },
      max_wash_temperature_c: { value: null, status: 'needs_confirmation', source: 'care_label' },
    },
    care_guidance: ['손세탁하세요.', '찬물로 세탁하세요.'],
    care_guidance_source: 'care_label',
  });
  assert.equal(result.waterText, '찬물로 세탁하세요.');
  assert.deepEqual(careSummary(result.care, result.waterText).map((c) => c.label), ['세탁 방법', '물 온도']);
  assert.equal(result.care.careNotes, '손세탁하세요.\n찬물로 세탁하세요.');
});

test('a numeric temperature cell wins over the worded water reading', () => {
  const cells = careSummary({ wash: 'machine', maxTemp: 30 }, '찬물로 세탁하세요.');
  assert.deepEqual(cells.map((c) => c.label), ['세탁 방법', '최대 온도']);
});

test('label fibre tips are material guidance and never saved as care notes', () => {
  const withLabel = labelResponse({
    care_label: {
      wash_method: { value: 'hand_wash', status: 'read_from_label', source: 'care_label' },
      fiber_content: { value: '울 100%', status: 'read_from_label', source: 'care_label' },
    },
    care_guidance: ['손세탁하세요.', '소재 기준 권장: 물 온도 · 찬물에서 다루세요.'],
    care_guidance_source: 'care_label',
  });
  assert.equal(withLabel.status, 'label');
  assert.deepEqual(withLabel.guidance, ['손세탁하세요.']);
  assert.deepEqual(withLabel.materialGuidance, ['물 온도 · 찬물에서 다루세요.']);
  assert.equal(withLabel.care.careNotes, '손세탁하세요.');

  const fibreOnly = labelResponse({
    care_label: { fiber_content: { value: '면 100%', status: 'read_from_label', source: 'care_label' } },
    care_guidance: ['소재 기준 권장: 건조 · 그늘에서 말리세요.'],
    care_guidance_source: 'material_estimate',
  });
  assert.deepEqual(fibreOnly.materialGuidance, ['건조 · 그늘에서 말리세요.']);
  assert.deepEqual(fibreOnly.guidance, []);
  assert.equal(fibreOnly.care.careNotes, undefined);
});
