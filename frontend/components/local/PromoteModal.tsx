'use client';
import { useCallback, useEffect, useState } from 'react';
import { localApi } from '@/api/local';
import { PromotionTariff } from '@/lib/types';
import { getErrorMessage } from '@/lib/errors';
import Modal from '@/components/ui/Modal';
import ErrorState from '@/components/ui/ErrorState';
import LoadingState from '@/components/ui/LoadingState';

interface Props {
  listingId: number;
  listingTitle: string;
  defaultType?: 'renew' | 'bump' | 'top';
  onClose: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  renew: 'Продовження',
  bump: 'Підняти',
  top: 'ТОП',
};

const TYPE_ICONS: Record<string, string> = {
  renew: '🔄',
  bump: '⬆️',
  top: '⭐',
};

export default function PromoteModal({ listingId, listingTitle, defaultType, onClose }: Props) {
  const [tariffs, setTariffs] = useState<PromotionTariff[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState<unknown>(null);

  const loadTariffs = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    void localApi.tariffs()
      .then(data => {
        setTariffs(data);
        const first = defaultType ? data.find(t => t.type === defaultType) : data[0];
        if (first) setSelected(first.code);
      })
      .catch(setLoadError)
      .finally(() => setLoading(false));
  }, [defaultType]);

  useEffect(() => {
    loadTariffs();
  }, [loadTariffs]);

  async function handlePay() {
    if (!selected) return;
    setPaying(true);
    setError('');
    try {
      const checkout = await localApi.promote(listingId, selected);
      // Redirect to LiqPay hosted checkout page
      window.location.href = checkout.checkout_url;
    } catch (err: unknown) {
      setError(getErrorMessage(err));
      setPaying(false);
    }
  }

  const selectedTariff = tariffs.find(t => t.code === selected);

  return (
    <Modal title="Просування оголошення" onClose={onClose} showClose>
      <div>
        <div>
          <p className="text-sm text-muted-foreground mb-4 truncate">{listingTitle}</p>

          {/* Sandbox notice */}
          <div className="bg-warning/15 border border-warning rounded-lg px-3 py-2 text-xs text-foreground mb-4">
            <strong>Тестовий режим (SANDBOX).</strong> Реальні гроші не списуються.
            Повноцінну оплату перевіримо на живому сервері.
          </div>

          {loading ? (
            <LoadingState size="md" />
          ) : loadError ? (
            <div className="mb-4"><ErrorState error={loadError} onRetry={loadTariffs} /></div>
          ) : tariffs.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-6">Просування тимчасово недоступне</p>
          ) : (
            <div className="space-y-2 mb-4">
              {tariffs.map(t => (
                <label
                  key={t.code}
                  className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                    selected === t.code ? 'border-ring bg-link/10' : 'border-border hover:border-input'
                  }`}
                >
                  <input
                    type="radio"
                    name="tariff"
                    value={t.code}
                    checked={selected === t.code}
                    onChange={() => setSelected(t.code)}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span aria-hidden="true">{TYPE_ICONS[t.type]}</span>
                      <span className="font-medium text-foreground text-sm">{t.name}</span>
                      <span className="ml-auto text-sm font-bold text-link whitespace-nowrap">
                        {Number(t.price).toLocaleString('uk-UA')} {t.currency}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{t.description}</p>
                    <span className="inline-block mt-1 text-[11px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
                      {TYPE_LABELS[t.type]}
                      {t.duration_days > 0 ? ` · ${t.duration_days} дн.` : ''}
                    </span>
                  </div>
                </label>
              ))}
            </div>
          )}

          {error && <p role="alert" className="text-xs text-destructive mb-3">{error}</p>}

          <div className="flex gap-2">
            <button
              onClick={handlePay}
              disabled={!selected || paying}
              className="flex-1 bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-semibold py-2.5 rounded-xl text-sm transition-colors"
            >
              {paying ? 'Перехід до оплати...' : `Оплатити${selectedTariff ? ` ${Number(selectedTariff.price).toLocaleString('uk-UA')} ${selectedTariff.currency}` : ''}`}
            </button>
            <button
              onClick={onClose}
              className="px-4 border border-border rounded-xl text-sm text-muted-foreground hover:bg-muted transition-colors"
            >
              Скасувати
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
