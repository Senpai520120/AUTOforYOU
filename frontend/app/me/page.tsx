import { serverGetAuthed } from '@/lib/server-api';
import type { User } from '@/lib/types';
import MeDashboard from './MeDashboard';

// serverGetAuthed читає cookie відвідувача — сторінку не можна пререндерити й кешувати.
export const dynamic = 'force-dynamic';

export default async function MePage() {
  // Перевірка авторизованого SSR (задача 1.4): сервер бачить сесію з cookie `access`.
  // Сам кабінет поки рендериться на клієнті; на SSR переводять задачі, яким це треба (2.9).
  const ssrUser = await serverGetAuthed<User>('/api/v1/auth/profile/');
  return (
    <div data-ssr-auth={ssrUser ? 'user' : 'guest'}>
      <MeDashboard />
    </div>
  );
}
