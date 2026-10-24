import { useEffect, useRef } from "react";

export function AgeRestricted({
  onCorrectDate,
  onBack,
}: {
  onCorrectDate: () => void;
  onBack: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    window.scrollTo(0, 0);
    heading.current?.focus({ preventScroll: true });
  }, []);
  return (
    <section className="age-restricted" aria-labelledby="age-restricted-title">
      <p className="brand">Очаково: изнутри</p>
      <div className="age-restricted-art">
        <span className="age-restricted-badge" aria-label="С 18 лет">
          18+
        </span>
        <img
          src="/assets/mascot-sad.png"
          alt="Грустная открывашка ждёт будущей встречи"
          width="210"
          height="260"
        />
      </div>
      <div className="age-restricted-copy">
        <p className="eyebrow">КАЖДОМУ ОТКРЫТИЮ — СВОЁ ВРЕМЯ</p>
        <h1 id="age-restricted-title" ref={heading} tabIndex={-1}>
          Наше знакомство
          <br />
          ещё впереди
        </h1>
        <p className="age-restricted-speech">
          Мне тоже жаль, что пока не получится познакомиться.
        </p>
        <p className="muted">
          Практика и регистрация доступны с 18 лет. Возвращайся, когда
          исполнится 18 — откроем твой путь к делу вместе.
        </p>
      </div>
      <div className="age-restricted-actions">
        <button
          type="button"
          className="button button-primary"
          onClick={onBack}
        >
          До встречи!
        </button>
        <button type="button" className="button-ghost" onClick={onCorrectDate}>
          Ошибка в дате рождения?
        </button>
      </div>
    </section>
  );
}
