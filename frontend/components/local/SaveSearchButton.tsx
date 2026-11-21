'use client';
import { useId, useState } from 'react';
import Modal from '@/components/ui/Modal';
import { useSearchParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { createSavedSearch } from '@/api/saved-searches';
import { CircleAlert, CircleCheck, Search } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { ICON_STROKE } from '@/lib/utils';

export default function SaveSearchButton() {
  const { user } = useAuth();
  const router = useRouter();
  const nameId = useId();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [notify, setNotify] = useState(true);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  const hasFilters = Array.from(searchParams.keys()).some(k => k !== 'page');

  if (!hasFilters) return null;

  const handleOpen = () => {
    if (!user) { router.push('/login'); return; }
    // Auto-suggest name from active filters
    const make = searchParams.get('make') ?? '';
    const model = searchParams.get('model') ?? '';
    const yearMin = searchParams.get('year_min') ?? '';
    const parts = [make, model, yearMin ? `від ${yearMin}` : ''].filter(Boolean);
    setName(parts.join(' ') || 'Мій пошук');
    setDone(false);
    setError('');
    setOpen(true);
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError('');
    const filters: Record<string, string> = {};
    searchParams.forEach((value, key) => {
      if (key !== 'page') filters[key] = value;
    });
    try {
      await createSavedSearch(name.trim(), filters, notify);
      setDone(true);
      setTimeout(() => setOpen(false), 1500);
    } catch {
      setError('Не вдалось зберегти. Спробуйте ще раз.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button type="button" variant="outline" onClick={handleOpen} className="border-primary text-primary hover:bg-primary/5 hover:text-primary">
        <Search strokeWidth={ICON_STROKE} aria-hidden="true" />
        Зберегти пошук
      </Button>

      {open && (
        <Modal title="Зберегти пошук" onClose={() => setOpen(false)} maxWidth="max-w-sm">
          <div>
            {done ? (
              <div className="text-center py-4">
                <CircleCheck className="mx-auto mb-2 size-10 text-success" strokeWidth={ICON_STROKE} aria-hidden="true" />
                <p className="font-semibold text-foreground">Пошук збережено!</p>
                <p className="text-xs text-muted-foreground mt-1">Перегляньте у «Збережені пошуки»</p>
              </div>
            ) : (
              <>
                {error && (
                  <div role="alert" className="mb-3 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                    <CircleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
                    {error}
                  </div>
                )}
                <Label htmlFor={nameId} className="mb-1.5">Назва</Label>
                <Input
                  id={nameId}
                  value={name}
                  onChange={e => setName(e.target.value)}
                  autoFocus
                />
                <label className="flex items-center gap-2 mt-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={notify}
                    onChange={e => setNotify(e.target.checked)}
                    className="size-4 rounded accent-primary"
                  />
                  <span className="text-sm text-foreground">Отримувати сповіщення про нові авто</span>
                </label>
                <p className="text-xs text-muted-foreground mt-1 ml-6">Раз на день, якщо з&apos;являться нові оголошення</p>
                <div className="flex gap-2 mt-4">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)} className="flex-1">
                    Скасувати
                  </Button>
                  <Button type="button" onClick={handleSave} disabled={!name.trim() || saving} className="flex-1 font-semibold">
                    {saving ? 'Збереження…' : 'Зберегти'}
                  </Button>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
