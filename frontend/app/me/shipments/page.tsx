'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { meApi } from '@/api/me';
import { Shipment } from '@/lib/types';
import Spinner from '@/components/ui/Spinner';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';

const STATUS_STEPS = [
  'at_us_warehouse', 'loading', 'in_ocean',
  'at_eu_port', 'on_truck_to_ua', 'cleared', 'delivered',
];

const STATUS_LABELS: Record<string, string> = {
  at_us_warehouse: 'Склад США',
  loading: 'Погрузка',
  in_ocean: 'В морі 🌊',
  at_eu_port: 'Порт ЄС',
  on_truck_to_ua: 'Автовоз → UA',
  cleared: 'Розмитнено',
  delivered: 'Доставлено ✅',
};

export default function MyShipmentsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) { router.push('/login'); return; }
    if (user) meApi.shipments().then(d => setShipments(d.results)).finally(() => setFetching(false));
  }, [user, loading, router]);

  if (loading || fetching) return <div className="flex justify-center py-20"><Spinner /></div>;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/me" className="text-blue-600 hover:underline text-sm">← Кабінет</Link>
        <h1 className="text-xl font-bold text-slate-900">Мої контейнери</h1>
      </div>

      {shipments.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-400 text-lg">Відстежуваних контейнерів немає</p>
          <p className="text-slate-400 text-sm mt-2">Зверніться до менеджера щоб додати контейнер</p>
        </div>
      ) : (
        <div className="space-y-4">
          {shipments.map(s => {
            const step = STATUS_STEPS.indexOf(s.status);
            return (
              <div key={s.id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <p className="font-bold text-slate-900 text-lg">{s.container_no}</p>
                    {s.vessel && <p className="text-sm text-slate-500">{s.vessel}</p>}
                  </div>
                  <div className="text-right">
                    <Badge variant={s.status === 'delivered' ? 'success' : 'info'}>
                      {STATUS_LABELS[s.status] ?? s.status}
                    </Badge>
                    {s.eta && <p className="text-xs text-slate-400 mt-1">ETA: {s.eta}</p>}
                  </div>
                </div>
                {/* Progress bar */}
                <div className="flex gap-1 mt-3">
                  {STATUS_STEPS.map((st, i) => (
                    <div key={st} title={STATUS_LABELS[st]}
                      className={`flex-1 h-2 rounded-full transition-colors ${i <= step ? 'bg-blue-600' : 'bg-slate-200'}`} />
                  ))}
                </div>
                <p className="text-xs text-slate-400 mt-1">{step + 1} / {STATUS_STEPS.length} кроків</p>
                <p className="text-xs text-slate-500 mt-2">
                  {s.vehicle_count} авто · порт: {s.arrival_port_eu}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
