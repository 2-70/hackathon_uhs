export type Garment = {
  id: string;
  name: string;
  category: string;
  color: string;
  material: string;
  wash: 'machine' | 'hand' | 'none' | 'unknown';
  maxTemp: number | null;
  maxSpin?: number | null;
  washStrength?: 'normal' | 'gentle' | 'very_gentle' | null;
  gentle: boolean | null;
  dryer: 'yes' | 'no' | 'unknown';
  drying: string;
  source: 'manual' | 'sample-label' | 'sample-product' | 'care-label' | 'official-product';
  sourceReference?: string;
  careNotes?: string;
  photo?: string;
  labelPhoto?: string;
  washSeparately?: boolean | null;
  colorBleedRisk?: boolean | null;
};

export type GarmentDraft = Omit<Garment, 'id'>;
export type GarmentPhotos = Partial<Record<'clothing' | 'label', string>>;

export type Course = {
  id: string;
  name: string;
  panelName?: string;
  gentle: boolean;
  settings: { temp: number; spin: number }[];
  verifiedSettings?: VerifiedSetting[];
};

export type VerifiedSetting = {
  id: string;
  temperature: string;
  spin: string;
  temperatureCelsius: number | null;
  spinRpm: number | null;
  washStrength: Garment['washStrength'];
  waterLevel: string | null;
  dryLevel: string | null;
  isDefault: boolean;
  sourceUrl: string | null;
  manualPage: number | null;
};

export type MachineChoice = {
  id: string;
  maker: string;
  model: string;
  sourceUrl?: string | null;
  catalog?: { capacityKg: number | null; hasManual: boolean };
};

export type MachineDocument = { id: string; title: string | null; url: string };
export type MachineInstruction = { id: string; title: string; text: string | null; url: string };

export type Machine = MachineChoice & {
  courses: Course[];
  documents?: MachineDocument[];
  instructions?: MachineInstruction[];
};

export type Plan = {
  groups: {
    id: string;
    garments: Garment[];
    course: Course;
    temp: number;
    spin: number;
    reason: string;
  }[];
  excluded: { garment: Garment; reason: string }[];
};
