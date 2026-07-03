'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { localApi } from '@/api/local';
import { dealsApi } from '@/api/deals';
import { LocalListing } from '@/lib/types';
import PromoteModal from '@/components/local/PromoteModal';

interface Buyer { id: number; email: string; first_name: string; last_name: string; }
interface SoldModalState { listing: LocalListing; buyers: Buyer[]; loading: boolean; }

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  active:   { label: 'Активне',         cls: 'bg-green-100 text-green-800' },
  pending:  { label: 'На модерації',    cls: 'bg-amber-100 text-amber-800' },
  rejected: { label: 'Відхилено',       cls: 'bg-red-100 text-red-800' },
  hidden:   { label: 'Приховане',       cls: 'bg-slate-100 text-slate-600' },
  sold:     { label: 'Продано',         cls: 'bg-blue-100 text-blue-800' },
  expired:  { label: 'Закінчилося',     cls: 'bg-slate-100 text-slate-500' },
  draft:    { label: 'Чернетка',        cls: 'bg-slate-100 text-slate-500' },
};

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  return Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86400000);
}

interface ModalState {
  listingId: number;
  listingTitle: string;
  defaultType: 'renew' | 'bump' | 'top';
}

export default function MyLocalListingsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [listings, setListings] = useState<LocalListing[]>([]);
  const [fetching, setFetching] = useState(true);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [soldModal, setSoldModal] = useState<SoldModalState | null>(null);
  const [proposingTo, setProposingTo] = useState<number | null>(null);
  const [soldError, setSoldError] = useState('');

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    localApi
      .myListings()
      .then(data => setListings(data.results))
      .catch(() => {})
      .finally(() => setFetching(false));
  }, [user]);

  async function handleDelete(id: number) {
    if (!confirm('Видалити оголошення?')) return;
    try {
      await localApi.remove(id);
      setListings(prev => prev.filter(l => l.id !== id));
    } catch {
      alert('Не вдалося видалити.');
    }
  }

  async function openSoldModal(l: LocalListing) {
    setSoldModal({ listing: l, buyers: [], loading: true });
    setSoldError('');
    try {
      const buyers = await dealsApi.listingBuyers(l.id);
      setSoldModal({ listing: l, buyers, loading: false });
    } catch {
      setSoldModal(prev => prev ? { ...prev, loading: false } : null);
    }
  }

  async function handleProposeDeal(buyerId: number) {
    if (!soldModal) return;
    setProposingTo(buyerId);
    setSoldError('');
    try {
      await dealsApi.propose(soldModal.listing.id, buyerId);
      setSoldModal(null);
      alert('Пропозицію угоди надіслано покупцю!');
    } catch (err: unknown) {
      const e = err as { data?: { detail?: string } };
      setSoldError(e?.data?.detail || 'Не вдалося запропонувати угоду.');
    } finally {
      setProposingTo(null);
    }
  }

  function openPromote(l: LocalListing, type: 'renew' | 'bump' | 'top') {
    setModal({ listingId: l.id, listingTitle: `${l.make} ${l.model} ${l.year}`, defaultType: type });
  }

  if (loading || fetching) return <div className="text-center py-20 text-slate-400">Завантаження...</div>;

  return (
    <div className="max-w-3xl mx-auto">
      {modal && (
        <PromoteModal
          listingId={modal.listingId}
          listingTitle={modal.listingTitle}
          defaultType={modal.defaultType}
          onClose={() => setModal(null)}
        />
      )}

      {/* Sold / Propose Deal Modal */}
      {soldModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-bold mb-1">Позначити як продано</h3>
            <p className="text-sm text-slate-500 mb-4">
              {soldModal.listing.make} {soldModal.listing.model} {soldModal.listing.year} — оберіть покупця:
            </p>
            {soldModal.loading && <p className="text-slate-400 text-sm py-4 text-center">Завантаження...</p>}
            {!soldModal.loading && soldModal.buyers.length === 0 && (
              <p className="text-slate-500 text-sm py-3 text-center">Ніхто ще не писав по цьому оголошенню.</p>
            )}
            {soldError && <p className="text-red-600 text-sm mb-2">{soldError}</p>}
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {soldModal.buyers.map(b => (
                <button
                  key={b.id}
                  onClick={() => handleProposeDeal(b.id)}
                  disabled={proposingTo === b.id}
                  className="w-full flex items-center justify-between border border-slate-200 hover:bg-blue-50 rounded-lg px-4 py-2.5 text-sm text-left disabled:opacity-60"
                >
                  <span>{b.first_name ? `${b.first_name} ${b.last_name}`.trim() : b.email}</span>
                  <span className="text-xs text-slate-400">{b.email}</span>
                </button>
              ))}
            </div>
            <button
              onClick={() => setSoldModal(null)}
              className="mt-4 w-full text-sm text-slate-500 hover:text-slate-700"
            >
              Закрити
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Мої оголошення</h1>
        <Link
          href="/local/new"
          className="bg-amber-500 hover:bg-amber-400 text-black font-semibold px-4 py-2 rounded-lg text-sm"
        >
          + Нове оголошення
        </Link>
      </div>

      {listings.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <p className="text-4xl mb-3">📋</p>
          <p className="font-medium text-slate-600">Оголошень ще немає</p>
          <Link href="/local/new" className="mt-2 inline-block text-blue-600 underline text-sm">
            Подати перше оголошення
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {listings.map(l => {
            const badge = STATUS_BADGE[l.status] ?? { label: l.status, cls: 'bg-slate-100 text-slate-500' };
            const daysLeft = daysUntil(l.expires_at);
            const expiringSoon = l.status === 'active' && daysLeft !== null && daysLeft <= 3 && daysLeft >= 0;
            const isTop = l.promoted_until && new Date(l.promoted_until) > new Date();

            return (
              <div key={l.id} className={`bg-white border rounded-xl p-4 ${expiringSoon ? 'border-amber-300' : 'border-slate-200'}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link href={`/local/${l.id}`} className="font-semibold text-slate-900 hover:text-blue-700">
                        {l.make} {l.model} {l.year}
                      </Link>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
                        {badge.label}
                      </span>
                      {isTop && (
                        <span className="text-xs px-2 py-0.5 rounded-full font-bold bg-amber-100 text-amber-800">
                          ⭐ ТОП
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">
                      {Number(l.price).toLocaleString('uk-UA')} {l.currency}
                      {' · '}{l.city_name}, {l.region_name}
                      {' · '}{l.mileage_km.toLocaleString()} км
                    </p>

                    {/* Термін дії */}
                    {l.expires_at && l.status === 'active' && daysLeft !== null && (
                      <p className={`mt-1 text-xs ${expiringSoon ? 'text-amber-700 font-medium' : 'text-slate-400'}`}>
                        {expiringSoon ? '⚠️ ' : ''}
                        Дійсне до {new Date(l.expires_at).toLocaleDateString('uk-UA')}
                        {daysLeft > 0 ? ` (${daysLeft} дн.)` : ' — закінчується сьогодні'}
                      </p>
                    )}
                    {l.status === 'expired' && (
                      <p className="mt-1 text-xs text-red-600">Термін дії закінчився. Продовжте оголошення.</p>
                    )}

                    {/* Причина відхилення */}
                    {l.status === 'rejected' && l.rejection_reason && (
                      <div className="mt-2 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
                        <strong>Причина відхилення:</strong> {l.rejection_reason}
                      </div>
                    )}

                    {l.status === 'pending' && (
                      <p className="mt-2 text-xs text-amber-700 bg-amber-50 rounded px-2 py-1 inline-block">
                        Очікує перевірки модератором
                      </p>
                    )}
                  </div>

                  <span className="text-xs text-slate-400 whitespace-nowrap">
                    {new Date(l.created_at).toLocaleDateString('uk-UA')}
                  </span>
                </div>

                {/* Actions */}
                <div className="mt-3 flex gap-2 flex-wrap">
                  {l.status === 'rejected' ? (
                    <Link
                      href={`/local/${l.id}/edit`}
                      className="text-sm bg-blue-700 hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Редагувати і надіслати знову
                    </Link>
                  ) : (l.status === 'active' || l.status === 'pending' || l.status === 'hidden') ? (
                    <Link
                      href={`/local/${l.id}/edit`}
                      className="text-sm border border-slate-300 hover:bg-slate-50 text-slate-700 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Редагувати
                    </Link>
                  ) : null}

                  {/* Кнопки просування */}
                  {l.status === 'expired' && (
                    <button
                      onClick={() => openPromote(l, 'renew')}
                      className="text-sm bg-green-600 hover:bg-green-500 text-white px-3 py-1.5 rounded-lg transition-colors"
                    >
                      🔄 Продовжити
                    </button>
                  )}
                  {l.status === 'active' && expiringSoon && (
                    <button
                      onClick={() => openPromote(l, 'renew')}
                      className="text-sm border border-amber-400 bg-amber-50 hover:bg-amber-100 text-amber-800 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      🔄 Продовжити (скоро закінчиться)
                    </button>
                  )}
                  {l.status === 'active' && (
                    <>
                      <button
                        onClick={() => openSoldModal(l)}
                        className="text-sm bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded-lg transition-colors"
                      >
                        ✅ Позначити проданим
                      </button>
                      <button
                        onClick={() => openPromote(l, 'bump')}
                        className="text-sm border border-blue-200 hover:bg-blue-50 text-blue-700 px-3 py-1.5 rounded-lg transition-colors"
                      >
                        ⬆️ Підняти
                      </button>
                      <button
                        onClick={() => openPromote(l, 'top')}
                        className="text-sm border border-amber-300 hover:bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg transition-colors"
                      >
                        ⭐ ТОП
                      </button>
                    </>
                  )}

                  {(l.status !== 'sold' && l.status !== 'expired') && (
                    <button
                      onClick={() => handleDelete(l.id)}
                      className="text-sm border border-red-200 hover:bg-red-50 text-red-600 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Видалити
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
