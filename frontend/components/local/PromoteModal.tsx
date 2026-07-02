'use client';
import { useEffect, useState } from 'react';
import { localApi } from '@/api/local';
import { PromotionTariff } from '@/lib/types';

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

  useEffect(() => {
    localApi.tariffs()
      .then(data => {
        setTariffs(data);
        const first = defaultType ? data.find(t => t.type === defaultType) : data[0];
        if (first) setSelected(first.code);
      })
      .catch(() => setError('Не вдалося завантажити тарифи.'))
      .finally(() => setLoading(false));
  }, [defaultType]);

  async function handlePay() {
    if (!selected) return;
    setPaying(true);
    setError('');
    try {
      const checkout = await localApi.promote(listingId, selected);
      // Redirect to LiqPay hosted checkout page
      window.location.href = checkout.checkout_url;
    } catch (err: unknown) {
      const e = err as { data?: { detail?: string } };
      setError(e?.data?.detail ?? 'Помилка при створенні платежу.');
      setPaying(false);
    }
  }

  const selectedTariff = tariffs.find(t => t.code === selected);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-slate-900">Просування оголошення</h2>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
          </div>
          <p className="text-sm text-slate-500 mb-4 truncate">{listingTitle}</p>

          {/* Sandbox notice */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800 mb-4">
            <strong>Тестовий режим (SANDBOX).</strong> Реальні гроші не списуються.
            Повноцінну оплату перевіримо на живому сервері.
          </div>

          {loading ? (
            <p className="text-slate-400 text-sm text-center py-4">Завантаження тарифів...</p>
          ) : (
            <div className="space-y-2 mb-4">
              {tariffs.map(t => (
                <label
                  key={t.code}
                  className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                    selected === t.code ? 'border-blue-500 bg-blue-50' : 'border-slate-200 hover:border-slate-300'
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
                      <span>{TYPE_ICONS[t.type]}</span>
                      <span className="font-medium text-slate-900 text-sm">{t.name}</span>
                      <span className="ml-auto text-sm font-bold text-blue-700 whitespace-nowrap">
                        {Number(t.price).toLocaleString('uk-UA')} {t.currency}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">{t.description}</p>
                    <span className="inline-block mt-1 text-[11px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                      {TYPE_LABELS[t.type]}
                      {t.duration_days > 0 ? ` · ${t.duration_days} дн.` : ''}
                    </span>
                  </div>
                </label>
              ))}
            </div>
          )}

          {error && <p className="text-xs text-red-600 mb-3">{error}</p>}

          <div className="flex gap-2">
            <button
              onClick={handlePay}
              disabled={!selected || paying}
              className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl text-sm transition-colors"
            >
              {paying ? 'Перехід до оплати...' : `Оплатити${selectedTariff ? ` ${Number(selectedTariff.price).toLocaleString('uk-UA')} ${selectedTariff.currency}` : ''}`}
            </button>
            <button
              onClick={onClose}
              className="px-4 border border-slate-200 rounded-xl text-sm text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Скасувати
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
