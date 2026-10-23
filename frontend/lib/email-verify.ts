import { apiPost, ApiError } from '@/api/client';

/** 403 з кодом email_not_verified: дія потребує підтвердженого email (задача 1.6). */
export function isEmailNotVerified(err: unknown): boolean {
  return err instanceof ApiError && err.status === 403
    && (err.data as { code?: string } | null)?.code === 'email_not_verified';
}

export function resendVerificationEmail() {
  return apiPost<unknown>('/api/v1/auth/verify-email/resend/');
}
