/** What jsdom is missing that this app uses.
 *
 * `matchMedia` is the only one. ThemeToggle asks the OS whether it prefers
 * dark, and jsdom does not implement the API at all -- not "returns false",
 * absent -- so any render that reaches the header throws. Answering "no
 * preference" is the honest stand-in: the tests here are about routing and
 * sessions, and the theme is not what they are asking about.
 */
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      media: query,
      matches: false,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
