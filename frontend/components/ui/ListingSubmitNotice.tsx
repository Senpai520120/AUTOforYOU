/**
 * Пояснення над формою входу/реєстрації, коли людина йшла подавати оголошення (`next=/local/new`, 10.25).
 * Без обіцянок щодо строків і цін: лише причина, чому показано вхід, і що реєстрація безкоштовна.
 */
export const LISTING_SUBMIT_PATH = '/local/new';

export function isListingSubmitNext(next: string): boolean {
  return next === LISTING_SUBMIT_PATH || next.startsWith(`${LISTING_SUBMIT_PATH}?`);
}

export default function ListingSubmitNotice() {
  return (
    <p data-testid="listing-submit-notice"
      className="mb-4 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-sm text-foreground">
      Щоб подати оголошення, увійдіть або зареєструйтесь. Реєстрація безкоштовна.
    </p>
  );
}
