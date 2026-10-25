'use client';
import { createContext, useContext } from 'react';
import { C2C_CLOSED, type C2CFlags } from '@/lib/c2c';

const C2CContext = createContext<C2CFlags>(C2C_CLOSED);

/** Прапорці C2C для клієнтських компонентів; значення приходить із кореневого layout (сервер). */
export function C2CProvider({ flags, children }: { flags: C2CFlags; children: React.ReactNode }) {
  return <C2CContext.Provider value={flags}>{children}</C2CContext.Provider>;
}

export function useC2C(): C2CFlags {
  return useContext(C2CContext);
}
