import { useEffect, useRef, useState } from "react";
import type { ReferralClient, ReferralInfo } from "./types";
import "./referrals.css";

export function ReferralCard({ client }: { client: ReferralClient }) {
  const [data, setData] = useState<ReferralInfo | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [copying, setCopying] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    let active = true;
    setError("");
    setData(null);
    setCopied(false);
    void client<ReferralInfo>("/referrals/me")
      .then((value) => {
        if (active) setData(value);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Не удалось загрузить код.",
          );
      });
    return () => {
      active = false;
      mounted.current = false;
    };
  }, [client, attempt]);
  async function copy() {
    if (!data || copying) return;
    setCopying(true);
    setCopied(false);
    setError("");
    try {
      if (!navigator.clipboard?.writeText)
        throw new Error("Выдели и скопируй код вручную из поля ниже.");
      await navigator.clipboard.writeText(data.code);
      if (mounted.current) setCopied(true);
    } catch {
      if (mounted.current)
        setError("Выдели и скопируй код вручную из поля ниже.");
    } finally {
      if (mounted.current) setCopying(false);
    }
  }
  return (
    <section className="card referral-card" aria-label="Пригласи кандидата">
      <h2>Пригласи кандидата</h2>
      <p>
        Поделись своим кодом. Кандидат сможет указать его при отклике — его
        резюме будет подсвечено для HR.
      </p>
      {data ? (
        <>
          <label className="referral-code-label">
            Твой код
            <input
              className="referral-code"
              readOnly
              value={data.code}
              onFocus={(event) => event.target.select()}
              aria-label="Твой реферальный код"
            />
          </label>
          <button
            className="button button-primary"
            type="button"
            onClick={() => {
              void copy();
            }}
            disabled={copying}
          >
            {copying ? "Копируем…" : "Скопировать код"}
          </button>
          <p className="referral-stat">
            Откликов с твоим кодом: {data.stats.applications}
          </p>
          <p className="referral-stat">
            Мерч ожидает выдачи: {data.stats.merchPending}. Выдано:{" "}
            {data.stats.merchIssued}.
          </p>
        </>
      ) : (
        !error && <p role="status">Загружаем код…</p>
      )}
      {error && (
        <p className="referral-error" role="alert">
          {error}
        </p>
      )}
      {error && !data && (
        <button
          className="button button-secondary"
          type="button"
          onClick={() => setAttempt((value) => value + 1)}
        >
          Повторить
        </button>
      )}
      {copied && <p role="status">Код скопирован</p>}
      <p className="referral-policy">
        Если приглашённый кандидат устроится, ты получишь мерч после
        подтверждения трудоустройства командой HR. Решение о найме принимает HR.
      </p>
    </section>
  );
}
