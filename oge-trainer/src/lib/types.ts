export type Role = 'student' | 'teacher';
export type SectionKind = 'matching' | 'tfn' | 'gap';
export type TaskKind = 'text' | 'choice' | 'matching';

export interface Section {
  id: string; title: string; subtitle: string | null; kind: SectionKind; instruction: string | null; sort: number;
}
export interface Passage { id: string; section_id: string; title: string | null; body: string; sort: number }
export interface ChoiceOption { value: string; label: string }
export interface MatchingOptions { letters: string[]; questions: string[] }
export interface Task {
  id: string; section_id: string; passage_id: string | null; sort: number; number: string | null;
  kind: TaskKind; prompt: string; word: string | null; options: ChoiceOption[] | MatchingOptions | null; topic: string | null;
}
export interface Catalog { sections: Section[]; passages: Passage[]; tasks: Task[] }

export interface Profile {
  id: string; display_name: string; login: string | null; role: Role; created_at?: string;
  last_active_at?: string | null; current_section_id?: string | null; current_passage_id?: string | null; current_task_id?: string | null;
}
export interface Attempt {
  id: number; user_id: string; task_id: string; section_id: string | null; answer: string;
  is_correct: boolean; score: number; max_score: number; created_at: string;
}
export interface CheckResult {
  correct: boolean; score: number; max_score: number; answers: string[]; explanation: string; items: boolean[];
}
export interface Solution { task_id: string; answers: string[]; explanation: string }
export interface OverviewRow {
  user_id: string; display_name: string; login: string | null; role: Role; created_at: string;
  last_active_at: string | null; current_section_id: string | null; current_passage_id: string | null; current_task_id: string | null;
  attempts_total: number; tasks_attempted: number; tasks_correct: number; tasks_wrong: number; first_try_correct: number;
}
export interface SignUpInput { login: string; password: string; displayName: string; teacherCode?: string }

export interface Api {
  mode: 'supabase' | 'demo';
  getProfile(): Promise<Profile | null>;
  onAuthChange(cb: () => void): () => void;
  signIn(login: string, password: string): Promise<void>;
  signUp(input: SignUpInput): Promise<{ needsConfirmation: boolean }>;
  signOut(): Promise<void>;
  becomeTeacher(code: string): Promise<boolean>;
  loadCatalog(): Promise<Catalog>;
  myAttempts(): Promise<Attempt[]>;
  checkAnswer(taskId: string, answer: string): Promise<CheckResult>;
  getSolutions(taskIds: string[]): Promise<Solution[]>;
  touch(sectionId: string, passageId: string): Promise<void>;
  teacherOverview(): Promise<OverviewRow[]>;
  studentProfile(userId: string): Promise<Profile | null>;
  studentAttempts(userId: string): Promise<Attempt[]>;
  subscribeAttempts(cb: (a: Attempt) => void): () => void;
}
