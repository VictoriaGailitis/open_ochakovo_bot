const labels: Record<string, string> = {
  "lab": "Практика в лаборатории →",
  "production": "Практика в цехе розлива →",
  "technology": "Практика в технологическом цехе →",
  "warehouse": "Практика на складе →",
  "automation": "Роль инженера по автоматизации →",
  "mechanics": "Роль наладчика линии →"
};

export function careerLabel(direction: string): string {
  return labels[direction] ?? "Познакомиться с ролью →";
}
