import { useEffect, useRef, useState } from "react";

interface NumberFieldProps {
  id: string;
  value: number;
  onChange: (value: number) => void;
  step?: string;
  min?: number;
  max?: number;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Numeric input that keeps a raw text draft while the field is focused, so a
 * user can fully clear it and retype (e.g. erase "28" and type "24") without a
 * stray "0" being injected. The parsed number is pushed up live on every valid
 * keystroke; on blur an empty/invalid draft reverts to the last good value.
 */
export function NumberField({
  id,
  value,
  onChange,
  step,
  min,
  max,
  disabled,
  placeholder,
}: NumberFieldProps) {
  const [draft, setDraft] = useState<string>(String(value));
  const focusedRef = useRef(false);

  useEffect(() => {
    if (!focusedRef.current) setDraft(String(value));
  }, [value]);

  return (
    <input
      id={id}
      type="number"
      inputMode="decimal"
      step={step}
      min={min}
      max={max}
      disabled={disabled}
      placeholder={placeholder}
      value={draft}
      onFocus={() => {
        focusedRef.current = true;
      }}
      onChange={(e) => {
        const raw = e.target.value;
        setDraft(raw);
        if (raw.trim() === "") return; // allow an empty field mid-edit
        const n = Number(raw);
        if (Number.isFinite(n)) onChange(n);
      }}
      onBlur={() => {
        focusedRef.current = false;
        const n = Number(draft);
        if (draft.trim() === "" || !Number.isFinite(n)) {
          setDraft(String(value)); // revert to last valid value
        } else {
          onChange(n);
          setDraft(String(n));
        }
      }}
    />
  );
}
