'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/lib/use-require-auth';
import { localApi } from '@/api/local';
import { dealsApi } from '@/api/deals';
import { LocalListing } from '@/lib/types';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ui/ErrorState';
import EmptyState from '@/components/ui/EmptyState';
import { getErrorMessage } from '@/lib/errors';
import Modal from '@/components/ui/Modal';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import PromoteModal from '@/components/local/PromoteModal';
import { useC2C } from '@/components/c2c/C2CProvider';

interface Buyer { id: number; display_name: string; }
interface SoldModalState { listing: LocalListing; buyers: Buyer[]; loading: boolean; }

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  active:   { label: 'Активне',         cls: 'bg-success/10 text-success' },
  pending:  { label: 'На модерації',    cls: 'bg-warning/15 text-foreground' },
  rejected: { label: 'Відхилено',       cls: 'bg-destructive/10 text-destructive' },
  hidden:   { label: 'Приховане',       cls: 'bg-muted text-muted-foreground' },
  sold:     { label: 'Продано',         cls: 'bg-link/10 text-link' },
  expired:  { label: 'Закінчилося',     cls: 'bg-muted text-muted-foreground' },
  draft:    { label: 'Чернетка',        cls: 'bg-muted text-muted-foreground' },
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
  const { user, loading } = useRequireAuth();
  // Платні послуги (просування) — лише при PAYMENTS_ENABLED; інакше кнопок немає.
  const payments = useC2C().paymentsEnabled;
  const [listings, setListings] = useState<LocalListing[]>([]);
  // 8.4: мінімум фото з /local/config/ — для плашки «додайте фото»; помилка конфігу плашку просто ховає.
  const [minPhotos, setMinPhotos] = useState(0);
  useEffect(() => {
    let alive = true;
    localApi.config().then((c) => { if (alive) setMinPhotos(c.min_photos ?? 0); }).catch(() => undefined);
    return () => { alive = false; };
  }, []);
  const [fetching, setFetching] = useState(true);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [soldModal, setSoldModal] = useState<SoldModalState | null>(null);
  const [proposingTo, setProposingTo] = useState<number | null>(null);
  const [soldError, setSoldError] = useState('');
  const [loadError, setLoadError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<LocalListing | null>(null);

  const load = useCallback(() => {
    setFetching(true);
    setLoadError(null);
    localApi
      .myListings()
      .then(data => setListings(data.results))
      .catch(setLoadError)
      .finally(() => setFetching(false));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function confirmDelete() {
    if (!toDelete) return;
    const target = toDelete;
    setActionError(null);
    setNotice(null);
    try {
      await localApi.remove(target.id);
      setListings(prev => prev.filter(l => l.id !== target.id));
    } catch (e) {
      setActionError(getErrorMessage(e));
    } finally {
      setToDelete(null);
    }
  }

  async function openSoldModal(l: LocalListing) {
    setSoldModal({ listing: l, buyers: [], loading: true });
    setSoldError('');
    try {
      const buyers = await dealsApi.listingBuyers(l.id);
      setSoldModal({ listing: l, buyers, loading: false });
    } catch (e) {
      setSoldModal(prev => prev ? { ...prev, loading: false } : null);
      setSoldError(getErrorMessage(e));
    }
  }

  async function handleProposeDeal(buyerId: number) {
    if (!soldModal) return;
    setProposingTo(buyerId);
    setSoldError('');
    try {
      await dealsApi.propose(soldModal.listing.id, buyerId);
      setSoldModal(null);
      setNotice('Пропозицію угоди надіслано покупцю!');
    } catch (err: unknown) {
      setSoldError(getErrorMessage(err));
    } finally {
      setProposingTo(null);
    }
  }

  function openPromote(l: LocalListing, type: 'renew' | 'bump' | 'top') {
    setModal({ listingId: l.id, listingTitle: `${l.make} ${l.model} ${l.year}`, defaultType: type });
  }

  if (loading || !user || fetching) return <LoadingState />;

  return (
    <div className="max-w-3xl mx-auto">
      {payments && modal && (
        <PromoteModal
          listingId={modal.listingId}
          listingTitle={modal.listingTitle}
          defaultType={modal.defaultType}
          onClose={() => setModal(null)}
        />
      )}

      {/* Sold / Propose Deal Modal */}
      {soldModal && (
        <Modal title="Позначити як продано" onClose={() => setSoldModal(null)}>
          <div>
            <p className="text-sm text-muted-foreground mb-4">
              {soldModal.listing.make} {soldModal.listing.model} {soldModal.listing.year} — оберіть покупця:
            </p>
            {soldModal.loading && <p className="text-muted-foreground text-sm py-4 text-center">Завантаження...</p>}
            {!soldModal.loading && soldModal.buyers.length === 0 && (
              <p className="text-muted-foreground text-sm py-3 text-center">Ніхто ще не писав по цьому оголошенню.</p>
            )}
            {soldError && <p role="alert" className="text-destructive text-sm mb-2">{soldError}</p>}
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {soldModal.buyers.map(b => (
                <button
                  key={b.id}
                  onClick={() => handleProposeDeal(b.id)}
                  disabled={proposingTo === b.id}
                  className="w-full flex items-center justify-between border border-border hover:bg-link/10 rounded-lg px-4 py-2.5 text-sm text-left disabled:opacity-60"
                >
                  <span>{b.display_name}</span>
                </button>
              ))}
            </div>
            <button
              onClick={() => setSoldModal(null)}
              className="mt-4 w-full text-sm text-muted-foreground hover:text-foreground"
            >
              Закрити
            </button>
          </div>
        </Modal>
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-foreground">Мої оголошення</h1>
        <Link
          href="/local/new"
          className="bg-accent hover:bg-accent/90 text-accent-foreground font-semibold px-4 py-2 rounded-lg text-sm"
        >
          + Нове оголошення
        </Link>
      </div>

      {actionError && <p role="alert" className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/40 rounded-lg px-3 py-2">{actionError}</p>}
      {notice && <p role="status" className="mb-4 text-sm text-success bg-success/10 border border-success/40 rounded-lg px-3 py-2">{notice}</p>}

      {loadError ? (
        <ErrorState error={loadError} onRetry={load} />
      ) : listings.length === 0 ? (
        <EmptyState icon="📋" title="Оголошень ще немає" hint="Подайте перше оголошення — це безкоштовно." action={{ label: 'Подати перше оголошення', href: '/local/new' }} />
      ) : (
        <div className="space-y-4">
          {listings.map(l => {
            const badge = STATUS_BADGE[l.status] ?? { label: l.status, cls: 'bg-muted text-muted-foreground' };
            const daysLeft = daysUntil(l.expires_at);
            const expiringSoon = l.status === 'active' && daysLeft !== null && daysLeft <= 3 && daysLeft >= 0;
            const isTop = l.promoted_until && new Date(l.promoted_until) > new Date();

            return (
              <div key={l.id} className={`bg-card border rounded-xl p-4 ${expiringSoon ? 'border-warning' : 'border-border'}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link href={`/local/${l.id}`} className="font-semibold text-foreground hover:text-link">
                        {l.make} {l.model} {l.year}
                      </Link>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
                        {badge.label}
                      </span>
                      {isTop && (
                        <span className="text-xs px-2 py-0.5 rounded-full font-bold bg-warning/15 text-foreground">
                          ⭐ ТОП
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {Number(l.price).toLocaleString('uk-UA')} {l.currency}
                      {' · '}{l.city_name}, {l.region_name}
                      {' · '}{l.mileage_km.toLocaleString()} км
                    </p>

                    {/* Термін дії */}
                    {l.expires_at && l.status === 'active' && daysLeft !== null && (
                      <p className={`mt-1 text-xs ${expiringSoon ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                        {expiringSoon ? '⚠️ ' : ''}
                        Дійсне до {new Date(l.expires_at).toLocaleDateString('uk-UA')}
                        {daysLeft > 0 ? ` (${daysLeft} дн.)` : ' — закінчується сьогодні'}
                      </p>
                    )}
                    {payments && l.status === 'expired' && (
                      <p className="mt-1 text-xs text-destructive">Термін дії закінчився. Продовжте оголошення.</p>
                    )}

                    {/* Причина відхилення */}
                    {l.status === 'rejected' && l.rejection_reason && (
                      <div className="mt-2 bg-destructive/10 border border-destructive/40 rounded-lg p-3 text-sm text-destructive">
                        <strong>Причина відхилення:</strong> {l.rejection_reason}
                      </div>
                    )}

                    {l.status === 'pending' && (
                      <p className="mt-2 text-xs text-foreground bg-warning/15 rounded px-2 py-1 inline-block">
                        Очікує перевірки модератором
                      </p>
                    )}
                    {minPhotos > 0 && (l.status === 'pending' || l.status === 'draft')
                      && (l.photos_count ?? l.images.length) < minPhotos && (
                      <p role="status" className="mt-2 text-xs text-foreground bg-warning/15 border border-warning rounded px-2 py-1">
                        Додайте щонайменше {minPhotos} фото, щоб оголошення пройшло модерацію.{' '}
                        <Link href={`/local/${l.id}/edit`} className="underline">Додати фото</Link>
                      </p>
                    )}
                  </div>

                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(l.created_at).toLocaleDateString('uk-UA')}
                  </span>
                </div>

                {/* Actions */}
                <div className="mt-3 flex gap-2 flex-wrap">
                  {l.status === 'rejected' ? (
                    <Link
                      href={`/local/${l.id}/edit`}
                      className="text-sm bg-primary hover:bg-primary text-primary-foreground px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Редагувати і надіслати знову
                    </Link>
                  ) : (l.status === 'active' || l.status === 'pending' || l.status === 'hidden') ? (
                    <Link
                      href={`/local/${l.id}/edit`}
                      className="text-sm border border-input hover:bg-muted text-foreground px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Редагувати
                    </Link>
                  ) : null}

                  {/* Кнопки просування */}
                  {payments && l.status === 'expired' && (
                    <button
                      onClick={() => openPromote(l, 'renew')}
                      className="text-sm bg-success hover:bg-success text-success-foreground px-3 py-1.5 rounded-lg transition-colors"
                    >
                      🔄 Продовжити
                    </button>
                  )}
                  {payments && l.status === 'active' && expiringSoon && (
                    <button
                      onClick={() => openPromote(l, 'renew')}
                      className="text-sm border border-warning bg-warning/15 hover:bg-warning/15 text-foreground px-3 py-1.5 rounded-lg transition-colors"
                    >
                      🔄 Продовжити (скоро закінчиться)
                    </button>
                  )}
                  {l.status === 'active' && (
                    <>
                      <button
                        onClick={() => openSoldModal(l)}
                        className="text-sm bg-success hover:bg-success text-success-foreground px-3 py-1.5 rounded-lg transition-colors"
                      >
                        ✅ Позначити проданим
                      </button>
                      {payments && (
<button
                        onClick={() => openPromote(l, 'bump')}
                        className="text-sm border border-link/40 hover:bg-link/10 text-link px-3 py-1.5 rounded-lg transition-colors"
                      >
                        ⬆️ Підняти
                      </button>
                      )}
                      {payments && (
<button
                        onClick={() => openPromote(l, 'top')}
                        className="text-sm border border-warning hover:bg-warning/15 text-foreground px-3 py-1.5 rounded-lg transition-colors"
                      >
                        ⭐ ТОП
                      </button>
                      )}
                    </>
                  )}

                  {(l.status !== 'sold' && l.status !== 'expired') && (
                    <button
                      onClick={() => setToDelete(l)}
                      className="text-sm border border-destructive/40 hover:bg-destructive/10 text-destructive px-3 py-1.5 rounded-lg transition-colors"
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
      <ConfirmDialog
        open={toDelete !== null}
        title="Видалити оголошення?"
        message={toDelete ? `${toDelete.make} ${toDelete.model} ${toDelete.year}` : undefined}
        onConfirm={confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}
