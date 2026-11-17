'use client';
import { useEffect } from 'react';
import { trackLandingVisitOnce } from '@/lib/metrics';

/** Лічильник візитів лендингу (задача 9.50): нічого не показує, сторінка лишається серверною. */
export default function LandingVisitTracker() {
  useEffect(() => { trackLandingVisitOnce(); }, []);
  return null;
}
