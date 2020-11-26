/**
 * Cached page contents to avoid unnecessary HTTP requests.
 */
const PAGE_CACHE = new Map<string, string>();

/**
 * Functions to execute when pages are opened.
 */
const PAGE_HANDLERS = new Map<string, () => Promise<void>>();

/**
 * 
 * @param name Page name.
 * @param handler Handler to execute when the page is opened.
 */
export function registerPage(name: string, handler: () => Promise<void>) {
    PAGE_HANDLERS.set(name, handler);
}

/**
 * Gets page content HTML as string.
 * @param name Page name.
 */
async function getPage(name: string): Promise<string> {
    // Prefer in-memory cache
    if (PAGE_CACHE.has(name)) {
        return PAGE_CACHE.get(name)!;
    }

    // Get HTML from server and cache it
    const result = await fetch(`pages/${name}.html`);
    if (result.status != 200) {
        throw new Error('page not found: ' + result.status);
    }
    const content = await result.text();
    PAGE_CACHE.set(name, content);
    return content;
}

let currentPage: string;

/**
 * Changes the current page, replacing all content in body element.
 * @param name New page name.
 */
export async function changePage(name: string): Promise<void> {
    if (currentPage == name) {
        return; // No need to change anything
    }
    document.body.innerHTML = await getPage(name);

    // If page has open handler, execute it now
    if (PAGE_HANDLERS.has(name)) {
        PAGE_HANDLERS.get(name)!();
    }

    currentPage = name; // Change succeeded
}