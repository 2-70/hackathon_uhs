export type Garment = {
  id: string;
  name: string;
  category: string;
  color: string;
  material: string;
  wash: 'machine' | 'hand' | 'none' | 'unknown';
  maxTemp: number | null;
  gentle: boolean;
  dryer: 'yes' | 'no' | 'unknown';
  drying: string;
  source: 'manual' | 'sample-label' | 'sample-product';
  photo?: string;
};

export type GarmentDraft = Omit<Garment, 'id'>;

export type Course = {
  id: string;
  name: string;
  gentle: boolean;
  settings: { temp: number; spin: number }[];
};

export type Machine = {
  id: string;
  maker: string;
  model: string;
  courses: Course[];
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
