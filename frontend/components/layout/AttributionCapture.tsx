'use client';
import { Suspense, useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { captureAttribution } from '@/lib/attribution';

function Inner() {
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => { captureAttribution(); }, [pathname, search]);
  return null;
}

/** Зберігає джерело заходу (Н-26). Нічого не рендерить. */
export default function AttributionCapture() {
  return <Suspense fallback={null}><Inner /></Suspense>;
}
