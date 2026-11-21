'use client';
/**
 * Автодоповнення населеного пункту (задача 8.2, A3.2): combobox + listbox за ARIA.
 *
 * - запит лише від `minChars` символів (ліміти — з /local/config/), debounce, застарілі запити скасовуються;
 * - стрілки, Enter, Escape; вибір мишею/дотиком без втрати фокусу;
 * - «Пошук…», «Нічого не знайдено», помилка мережі — видимим текстом;
 * - зміна тексту після вибору скидає вибір (onChange(null)): форма не відправить «текст без пункту».
 * Чернетку нижньої частини (розмітка, клавіші) підготував Gemini, перевірено й доопрацьовано вручну.
 */
import { useEffect, useRef, useState } from 'react';
import { localApi } from '@/api/local';
import type { CityOption } from '@/lib/types';
import { FIELD_CLASS, FIELD_LABEL_CLASS } from './field-classes';

export type { CityOption };

const DEBOUNCE_MS = 250;

interface Props {
  id: string;
  label: string;
  value: CityOption | null;
  onChange: (city: CityOption | null) => void;
  regionId?: number;
  minChars: number;
  limit: number;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  inputClassName?: string;
  labelClassName?: string;
}

export default function CityAutocomplete({
  id, label, value, onChange, regionId, minChars, limit, error, disabled, required,
  placeholder = 'Почніть вводити назву', inputClassName, labelClassName,
}: Props) {
  const [query, setQuery] = useState(value?.label ?? '');
  const [options, setOptions] = useState<CityOption[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const abortRef = useRef<AbortController | null>(null);
  const blurTimer = useRef<number | undefined>(undefined);

  // Зовнішнє значення (редагування, скидання форми) показуємо в полі.
  const valueLabel = value?.label ?? null;
  const [shownValue, setShownValue] = useState(valueLabel);
  if (valueLabel !== shownValue) {
    setShownValue(valueLabel);
    if (valueLabel !== null) setQuery(valueLabel);
  }

  const term = query.trim();
  const typing = !value || query !== value.label;
  const active = typing && term.length >= minChars;

  useEffect(() => {
    if (!active) return;
    const timer = window.setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsLoading(true);
      setFetchError(null);
      localApi.searchCities({ q: term, region: regionId, limit }, controller.signal)
        .then((rows) => {
          if (controller.signal.aborted) return;
          setOptions(rows);
          setHighlightedIndex(rows.length ? 0 : -1);
          setSearched(true);
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setOptions([]);
          setFetchError('Не вдалося завантажити населені пункти. Спробуйте ще раз.');
          setSearched(true);
        })
        .finally(() => { if (!controller.signal.aborted) setIsLoading(false); });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [active, term, regionId, limit]);

  useEffect(() => () => { abortRef.current?.abort(); window.clearTimeout(blurTimer.current); }, []);

  const selectOption = (option: CityOption) => {
    abortRef.current?.abort();
    setQuery(option.label);
    setIsOpen(false);
    setHighlightedIndex(-1);
    onChange(option);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    setSearched(false);
    setOptions([]);
    if (value !== null) onChange(null);
    setIsOpen(true);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      setIsOpen(true);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (options.length) setHighlightedIndex((i) => (i + 1 >= options.length ? 0 : i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (options.length) setHighlightedIndex((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (e.key === 'Enter') {
      if (isOpen && highlightedIndex >= 0 && highlightedIndex < options.length) {
        e.preventDefault(); // не відправляти форму
        selectOption(options[highlightedIndex]);
      }
    } else if (e.key === 'Escape' && isOpen) {
      e.preventDefault();
      setIsOpen(false);
      setHighlightedIndex(-1);
    }
  };

  const listboxId = `${id}-listbox`;
  const showList = isOpen && active;
  const describedBy = [error ? `${id}-error` : '', `${id}-hint`].filter(Boolean).join(' ');

  return (
    <div className="relative w-full">
      <label htmlFor={id} className={labelClassName ?? FIELD_LABEL_CLASS}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-expanded={showList}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={showList && highlightedIndex >= 0 ? `${id}-option-${highlightedIndex}` : undefined}
        aria-describedby={describedBy}
        aria-invalid={Boolean(error)}
        aria-required={required || undefined}
        disabled={disabled}
        placeholder={placeholder}
        value={query}
        onChange={handleInputChange}
        onFocus={() => { window.clearTimeout(blurTimer.current); setIsOpen(true); }}
        // Закриття з затримкою: на iOS дотик знімає фокус раніше, ніж click по пункту встигає спрацювати.
        onBlur={() => { blurTimer.current = window.setTimeout(() => { setIsOpen(false); setHighlightedIndex(-1); }, 150); }}
        onKeyDown={handleKeyDown}
        className={inputClassName ?? FIELD_CLASS}
      />
      <p id={`${id}-hint`} className="sr-only">Введіть щонайменше {minChars} символи та оберіть пункт зі списку</p>

      {showList && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={label}
          className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-border bg-popover text-popover-foreground py-1 shadow-lg"
        >
          {isLoading && <li className="px-3 py-2 text-sm text-muted-foreground">Пошук…</li>}
          {!isLoading && fetchError && <li role="alert" className="px-3 py-2 text-sm text-destructive">{fetchError}</li>}
          {!isLoading && !fetchError && searched && options.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted-foreground">Нічого не знайдено. Перевірте написання.</li>
          )}
          {!isLoading && !fetchError && options.map((option, index) => (
            <li
              key={option.id}
              id={`${id}-option-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              // pointerdown тримає фокус у полі (на iOS blur приходить раніше за mousedown), вибір — по click
              onPointerDown={(e) => e.preventDefault()}
              onMouseDown={(e) => e.preventDefault()}
              onPointerUp={() => selectOption(option)}
              onClick={() => { if (value?.id !== option.id) selectOption(option); }}
              onMouseEnter={() => setHighlightedIndex(index)}
              className={`cursor-pointer px-3 py-2 text-sm ${index === highlightedIndex ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-secondary'}`}
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}

      {error && <p id={`${id}-error`} role="alert" className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
