export type MaterialCategory = "company" | "video" | "practice" | "stories";
export type MaterialAudience = "candidate" | "staff" | "all";
export type MaterialBlock =
  | { type: "text"; text: string }
  | { type: "heading"; text: string }
  | { type: "video"; mediaId: string; title: string }
  | { type: "image"; mediaId: string; alt: string };
export interface MaterialCompletion {
  materialId: string;
  version: number;
  completedAt: string;
  awardedPoints: number;
}
export interface MaterialSummary {
  id: string;
  title: string;
  description: string;
  category: MaterialCategory;
  audience: MaterialAudience;
  version: number;
  published: boolean;
  demo: boolean;
  points: number;
  questionCount: number;
  updatedAt: string;
  completion: MaterialCompletion | null;
}
export interface LearningQuestion {
  id: string;
  text: string;
  options: { id: string; text: string }[];
}
export interface Material extends MaterialSummary {
  blocks: MaterialBlock[];
  quiz: { points: number; questions: LearningQuestion[] } | null;
}
export interface MaterialResult {
  correct: boolean;
  errors: string[];
  pointsAwarded: number;
  alreadyCompleted: boolean;
  balance: number;
  completion?: MaterialCompletion;
  explanations?: { questionId: string; text: string }[];
}
