'use client';
import { useEffect, useRef } from 'react';

/**
 * setInterval, який стоїть на паузі, поки вкладка прихована
 * (document.visibilityState !== 'visible'), і робить негайний виклик
 * при поверненні на вкладку. Перший виклик при монтуванні — на боці споживача.
 */
export function useVisibleInterval(callback: () => void, ms: number, enabled = true) {
  const cbRef = useRef(callback);
  useEffect(() => { cbRef.current = callback; });

  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setInterval> | null = null;
    const stop = () => { if (timer !== null) { clearInterval(timer); timer = null; } };
    const start = () => {
      stop();
      timer = setInterval(() => {
        if (document.visibilityState === 'visible') cbRef.current();
      }, ms);
    };
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        cbRef.current();
        start();
      } else {
        stop();
      }
    };
    if (document.visibilityState === 'visible') start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      stop();
    };
  }, [ms, enabled]);
}
