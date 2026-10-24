export interface Mentor {
  id: string;
  name: string;
  position: string;
  contact: string;
  about: string;
  office_hours: string;
}
export type GoalStatus = "planned" | "in_progress" | "review" | "approved";
export interface Goal {
  id: string;
  title: string;
  description: string;
  criteria: string;
  due_date: string;
  status: GoalStatus;
  mentor_comment: string;
  version: number;
}
export interface Meeting {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  location: string;
  agenda: string;
  status: "scheduled" | "completed" | "cancelled";
  version: number;
}
export interface HelpRequest {
  id: string;
  target: "mentor" | "coordinator";
  topic: string;
  body: string;
  status: "received" | "in_progress" | "resolved";
  response: string;
  created: string;
  version: number;
}
export interface Checkin {
  id: string;
  week: string;
  answers: Record<string, number | string | null>;
  created: string;
}
export interface Placement {
  id: string;
  title: string;
  department: string;
  studentName: string;
  start_date: string;
  end_date: string;
  status: "scheduled" | "active" | "completed" | "cancelled";
  mentor: Mentor | null;
  coordinator: { name: string; contact: string } | null;
  arrival: string;
  onboarding: string[];
  documents: { title: string; status: string }[];
  goals: Goal[];
  meetings: Meeting[];
  feedback: {
    id: string;
    author_name: string;
    body: string;
    created: string;
  }[];
  requests: HelpRequest[];
  checkins?: Checkin[];
  career?: {
    interested: number;
    direction: string;
    schedule: string;
    comment: string;
    created: string;
  } | null;
}
export interface PracticeData {
  practices: Placement[];
  mentor: Mentor | null;
  mentees: Placement[];
  today: string;
  week: string;
}
