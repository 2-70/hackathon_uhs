import { request, washFromApi } from './api.ts';
import type { GarmentDraft } from './model';

export type PhotoKind = 'clothing' | 'label';
export type UploadPhoto = { uri: string; file?: File; fileName?: string | null; mimeType?: string; base64?: string | null };
type MatchedProduct = { name: string; source_url: string; product_code?: string | null };
export type Analysis = {
  status: 'exact' | 'label' | 'needs-confirmation';
  care: Partial<GarmentDraft>;
  guidance: string[];
  materialGuidance: string[];
  estimated: boolean;
  hasPublishedCare: boolean;
  message: string;
  searchNote?: string;
  productCode?: string | null;
  sourceUrl?: string;
  sourceLabel?: string;
  followUp?: PhotoKind;
  followUpInstructions?: string;
};

type Field = { value: string | number | boolean | null; status: string; source?: string };
type PhotoResponse = {
  image_type: 'garment' | 'care_label' | 'unknown';
  garment: Record<string, Field>;
  care_label: Record<string, Field>;
  product_care: Record<string, Field>;
  product_lookup: { status: string; product: MatchedProduct | null } | null;
  care_guidance: string[];
  care_guidance_source: 'official_product' | 'product_listing' | 'material_estimate' | 'estimated' | 'care_label' | null;
  search_warning?: string | null;
  photo_request: { image_type: 'garment' | 'care_label'; instructions: string } | null;
  message: string;
  next_actions?: string[];
};

const naturalDrying: Record<string, string> = {
  line_dry: '걸어서 말리기', drip_line_dry: '물이 떨어지는 상태로 걸어서 말리기',
  flat_dry: '평평하게 펴서 말리기', drip_flat_dry: '물이 떨어지는 상태로 평평하게 펴서 말리기',
};
const materialPrefix = '소재 기준 권장: ';

export function parseMaterialGuidance(line: string): { label: string; instruction: string } | null {
  const separator = line.indexOf(' · ');
  if (separator <= 0) return null;

  const label = line.slice(0, separator).trim();
  const instruction = line.slice(separator + 3).trim();
  return label && instruction ? { label, instruction } : null;
}

export function toAnalysis(response: PhotoResponse): Analysis {
  const product = response.product_lookup?.status === 'matched' ? response.product_lookup.product : null;
  const isLabel = response.image_type === 'care_label';
  const fields = product ? response.product_care : isLabel ? response.care_label : {};
  const confirmed = product ? 'verified' : 'read_from_label';
  const value = (key: string) => fields[key]?.status === confirmed ? fields[key].value : undefined;
  const text = (key: string) => { const entry = value(key); return typeof entry === 'string' ? entry : undefined; };
  const method = text('wash_method');
  const maxTemp = value('max_wash_temperature_c');
  const tumble = value('tumble_dry_allowed');
  const natural = text('natural_dry');
  const cycle = text('wash_cycle');
  const category = response.garment.garment_type?.value;
  const color = response.garment.color?.value;
  const instructions = response.photo_request?.instructions;
  const materialOnly = response.care_guidance_source === 'material_estimate';
  const materialGuidance = materialOnly
    ? response.care_guidance.map((line) => line.startsWith(materialPrefix) ? line.slice(materialPrefix.length) : line)
    : response.care_guidance.filter((line) => line.startsWith(materialPrefix)).map((line) => line.slice(materialPrefix.length));
  const genericEstimate = response.care_guidance_source === 'estimated';
  const estimated = genericEstimate && product === null;
  const guidance = response.care_guidance.filter((line) =>
    !line.startsWith(materialPrefix) && !materialOnly && !(genericEstimate && product !== null)
  );
  const lookupStatus = response.product_lookup?.status;
  const searchNote = response.search_warning ?? (
    lookupStatus === 'search_unavailable' ? '상품 검색에 연결하지 못했어요.'
      : lookupStatus === 'candidates' ? '검색 결과에서 같은 상품인지 확인하지 못했어요.'
      : lookupStatus === 'not_found' ? '검색에서 같은 상품을 찾지 못했어요.' : undefined
  );
  const hasLabelReadings = isLabel && Object.values(fields).some((field) => field.status === confirmed);
  const hasPublishedCare = product !== null && (
    (response.care_guidance_source === 'official_product' || response.care_guidance_source === 'product_listing')
      && guidance.length > 0
    || Object.entries(fields).some(([key, field]) =>
      key !== 'fiber_content' && field.status === confirmed && field.value !== null
    )
  );
  const productFieldSource = Object.values(fields).find((field) => field.source === 'product_listing' || field.source === 'official_product')?.source;
  const guidanceSource = response.care_guidance_source;
  const sourceLabel = productFieldSource === 'product_listing' || guidanceSource === 'product_listing'
    ? '판매처 상품 안내'
    : productFieldSource === 'official_product' || guidanceSource === 'official_product'
      ? '상품 공식 안내' : '상품 출처';
  const guidanceIsConfirmed = guidanceSource === 'official_product'
    || guidanceSource === 'product_listing' || guidanceSource === 'care_label';
  const care: Partial<GarmentDraft> = {
    name: product?.name,
    category: typeof category === 'string' ? category : undefined,
    color: typeof color === 'string' ? color : undefined,
    material: text('fiber_content'),
    wash: method ? washFromApi[method as keyof typeof washFromApi] : undefined,
    maxTemp: typeof maxTemp === 'number' ? maxTemp : undefined,
    washStrength: cycle === 'normal' || cycle === 'gentle' || cycle === 'very_gentle' ? cycle : undefined,
    gentle: cycle === 'normal' ? false : cycle === 'gentle' || cycle === 'very_gentle' ? true : undefined,
    dryer: typeof tumble === 'boolean' ? (tumble ? 'yes' : 'no') : undefined,
    drying: [natural ? naturalDrying[natural] : undefined, value('dry_in_shade') === true ? '그늘 건조' : undefined]
      .filter(Boolean).join(' · ') || undefined,
    careNotes: guidanceIsConfirmed ? guidance.join(' ').slice(0, 500) || undefined : undefined,
    source: product ? 'official-product' : hasLabelReadings ? 'care-label' : undefined,
    sourceReference: product?.source_url,
  };

  return {
    status: product ? 'exact' : hasLabelReadings ? 'label' : 'needs-confirmation',
    care, guidance, materialGuidance, estimated, hasPublishedCare, searchNote, sourceUrl: product?.source_url,
    productCode: product?.product_code,
    sourceLabel,
    message: instructions && !response.message.includes(instructions)
      ? `${response.message} ${instructions}` : response.message,
    followUp: product && !hasPublishedCare
      ? 'label'
      : response.photo_request
        ? response.photo_request.image_type === 'care_label' ? 'label' : 'clothing'
        : undefined,
    followUpInstructions: instructions,
  };
}

export async function analyzePhoto(kind: PhotoKind, photo: UploadPhoto, isWeb: boolean) {
  const form = new FormData();
  const name = photo.file?.name || photo.fileName || 'photo.jpg';
  if (isWeb) {
    const file = photo.file ?? await (await fetch(photo.uri)).blob();
    form.append('image', file, name);
  } else {
    form.append('image', { uri: photo.uri, name, type: photo.mimeType || 'image/jpeg' } as unknown as Blob);
  }
  form.append('image_type', kind === 'label' ? 'care_label' : 'auto');
  const response = await request<PhotoResponse>('/api/analyze', { method: 'POST', body: form }, 215000);
  return toAnalysis(response);
}
