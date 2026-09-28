export const BRAND = "Luxuria Gems";
export const HEADLINE = "Gems crafted to be remembered.";
export const LEDE = "Discover timeless pieces crafted to celebrate life's most precious moments.";
export const SITE_TITLE = `${BRAND} · ${HEADLINE.replace(/\.$/, "")}`;

export function pageTitle(page) {
  return page ? `${page} · ${BRAND}` : SITE_TITLE;
}
