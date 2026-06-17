export default function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const cls = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' }[size];
  return (
    <div className={`${cls} border-4 border-blue-200 border-t-blue-700 rounded-full animate-spin`} />
  );
}
