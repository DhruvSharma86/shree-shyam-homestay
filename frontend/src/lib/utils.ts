export function cn(...xs: (string | false | undefined)[]): string {
  return xs.filter(Boolean).join(' ');
}
