import { request, washFromApi } from './api';
import type { GarmentDraft } from './model';

export type PhotoKind = 'clothing' | 'label';
export type UploadPhoto = { uri: string; file?: File; fileName?: string | null; mimeType?: string };
export type Analysis = {
  status: 'exact' | 'label' | 'needs-confirmation';
  care: Partial<GarmentDraft>;
  guidance: string[];
  message: string;
  brand?: string;
  pattern?: string;
  sourceUrl?: string;
  followUp?: PhotoKind;
};

type Field = { value: string | number | boolean | null; status: string };
type PhotoResponse = {
  image_type: 'garment' | 'care_label' | 'unknown';
  garment: Record<string, Field>;
  care_label: Record<string, Field>;
  product_care: Record<string, Field>;
  product_lookup: { status: string; product: { name: string; source_url: string } | null } | null;
  care_guidance: string[];
  care_guidance_source: string | null;
  photo_request: { image_type: 'garment' | 'care_label'; instructions: string } | null;
  message: string;
};

const naturalDrying: Record<string, string> = {
  line_dry: '걸어서 말리기', drip_line_dry: '물이 떨어지는 상태로 걸어서 말리기',
  flat_dry: '평평하게 펴서 말리기', drip_flat_dry: '물이 떨어지는 상태로 평평하게 펴서 말리기',
};

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
  const brand = response.garment.brand?.value;
  const pattern = response.garment.pattern?.value;
  const instructions = response.photo_request?.instructions;
  const guidance = response.care_guidance_source === 'estimated' ? [] : response.care_guidance;
  const hasLabelReadings = isLabel && Object.values(fields).some((field) => field.status === confirmed);
  const care: Partial<GarmentDraft> = {
    name: product?.name,
    category: typeof category === 'string' ? category : undefined,
    color: typeof color === 'string' ? color : undefined,
    material: text('fiber_content'),
    wash: method ? washFromApi[method as keyof typeof washFromApi] : undefined,
    maxTemp: typeof maxTemp === 'number' ? maxTemp : undefined,
    gentle: cycle ? cycle === 'gentle' || cycle === 'very_gentle' : undefined,
    dryer: typeof tumble === 'boolean' ? (tumble ? 'yes' : 'no') : undefined,
    drying: [natural ? naturalDrying[natural] : undefined, value('dry_in_shade') === true ? '그늘 건조' : undefined]
      .filter(Boolean).join(' · ') || undefined,
    careNotes: guidance.join(' ').slice(0, 500) || undefined,
    source: product ? 'official-product' : hasLabelReadings ? 'care-label' : undefined,
    sourceReference: product?.source_url,
  };

  return {
    status: product ? 'exact' : hasLabelReadings ? 'label' : 'needs-confirmation',
    care, guidance, sourceUrl: product?.source_url,
    brand: typeof brand === 'string' ? brand : undefined,
    pattern: typeof pattern === 'string' ? pattern : undefined,
    message: instructions && !response.message.includes(instructions)
      ? `${response.message} ${instructions}` : response.message,
    followUp: response.photo_request
      ? response.photo_request.image_type === 'care_label' ? 'label' : 'clothing'
      : undefined,
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
  const response = await request<PhotoResponse>('/api/analyze', { method: 'POST', body: form }, 125000);
  return toAnalysis(response);
}
