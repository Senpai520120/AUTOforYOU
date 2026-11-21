type Variant = 'default' | 'success' | 'warning' | 'danger' | 'info';

// Текст завжди з контрастом >= 4.5:1 (див. docs/design/DESIGN_SYSTEM.md); статус дублюється текстом.
const styles: Record<Variant, string> = {
  default: 'bg-secondary text-secondary-foreground',
  success: 'bg-success text-success-foreground',
  warning: 'bg-warning text-warning-foreground',
  danger: 'bg-destructive/10 text-destructive',
  info: 'bg-primary/10 text-primary',
};

export default function Badge({ children, variant = 'default' }: {
  children: React.ReactNode;
  variant?: Variant;
}) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${styles[variant]}`}>
      {children}
    </span>
  );
}
