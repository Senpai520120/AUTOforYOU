'use client';

interface Props {
  publicId: string;
  onNew?: () => void;
  newLabel?: string;
}

export default function LeadSuccess({ publicId, onNew, newLabel = 'Новий розрахунок' }: Props) {
  return (
    <div role="status" data-testid="lead-success" className="text-center py-6">
      <div className="text-4xl mb-3" aria-hidden="true">✅</div>
      <h3 className="text-xl font-bold text-slate-900 mb-2">Заявку №{publicId} отримано</h3>
      <p className="text-slate-600 text-sm mb-2">
        Брокер зв&apos;яжеться з вами найближчим часом зручним для вас способом.
      </p>
      <p className="text-slate-700 text-sm mb-5">
        Назвіть менеджеру код <span className="font-mono font-bold">{publicId}</span>.
      </p>
      {onNew && (
        <button type="button" onClick={onNew}
          className="bg-blue-700 hover:bg-blue-800 text-white font-semibold px-6 py-2.5 rounded-xl transition-colors">
          {newLabel}
        </button>
      )}
    </div>
  );
}
