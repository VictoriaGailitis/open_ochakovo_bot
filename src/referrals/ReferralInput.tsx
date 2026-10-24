import { useId, useState } from "react";
import { validReferralCode } from "./types";
import "./referrals.css";

export function ReferralInput({
  value,
  onChange,
  disabled = false,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  error?: string;
}) {
  const id = useId();
  const [touched, setTouched] = useState(false);
  const message =
    error ||
    (touched && !validReferralCode(value)
      ? "Проверь код: OC- и 8 букв или цифр без пробелов."
      : "");
  return (
    <div className="referral-field">
      <label htmlFor={id}>
        Код пригласившего практиканта <span>(необязательно)</span>
      </label>
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value.toUpperCase())}
        onBlur={() => setTouched(true)}
        disabled={disabled}
        maxLength={64}
        autoCapitalize="characters"
        autoComplete="off"
        spellCheck={false}
        placeholder="OC-ABCDEFGH"
        aria-invalid={Boolean(message)}
        aria-describedby={`${id}-help${message ? ` ${id}-error` : ""}`}
      />
      <p id={`${id}-help`}>
        Если тебя пригласил практикант, укажи его код — твоё резюме будет
        подсвечено для HR.
      </p>
      {message && (
        <p id={`${id}-error`} className="referral-error" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
