type Variant = 'default' | 'success' | 'warning' | 'danger' | 'info';

const styles: Record<Variant, string> = {
  default: 'bg-slate-100 text-slate-700',
  success: 'bg-green-100 text-green-800',
  warning: 'bg-amber-100 text-amber-800',
  danger: 'bg-red-100 text-red-700',
  info: 'bg-blue-100 text-blue-800',
};

export default function Badge({ children, variant = 'default' }: {
  children: React.ReactNode;
  variant?: Variant;
}) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${styles[variant]}`}>
      {children}
    </span>
  );
}
