import DOMPurify from 'dompurify';

/**
 * Base token.
 */
interface Token {
    type: string;
    content: Token[];
}

/**
 * Token with plain-text value and empty content.
 */
interface TextToken extends Token {
    type: 'text';
    value: string;
}

/**
 * A paragraph token.
 */
interface ParagraphToken extends Token {
    type: 'paragraph';
}

/**
 * Token that applies a style to its content.
 */
interface StyleToken extends Token {
    type: 'style';
    style: 'em' | 'strong';
}

/**
 * Link to another passage.
 */
interface PassageLinkToken extends Token {
    type: 'passage';
    address: string;
}

export class ParserInput {
    /**
     * Underlying input string.
     */
    private _text: string;

    /**
     * Index of next character that has not been consumed yet.
     */
    private _offset: number;

    constructor(text: string) {
        this._text = text;
        this._offset = 0;
    }

    get text(): string {
        return this._text;
    }

    get offset(): number {
        return this._offset;
    }

    get end(): number {
        return this.text.length;
    }

    /**
     * Discards characters from the input.
     * @param count Character count.
     */
    discard(count: number): void {
        this._offset += count;
    }

    /**
     * Consumes characters from the input.
     * @param count Character count.
     * @returns Consumed characters in a string.
     */
    consume(count: number): ParserInput {
        const oldOffset = this._offset;
        this._offset += count;
        return new ParserInput(this.text.substring(oldOffset, this._offset));
    }

    /**
     * Finds first occurrance of given token string after current offset.
     * @param token Token string.
     * @returns Distance to current offset, or -1 if token was not found.
     */
    find(token: string): number {
        return this.text.indexOf(token, this.offset) - this.offset;
    }

    /**
     * Consumes the first occurrance of given token and characters before it.
     * The characters before are returned as string, the token itself is not.
     * @param token Token string.
     * @returns Characters between current offset and start of the token.
     */
    consumeUntil(token: string): ParserInput | undefined {
        const tokenStart = this.text.indexOf(token, this.offset);
        if (tokenStart == -1) {
            return undefined;
        }
        const oldOffset = this.offset;
        this._offset = tokenStart + token.length; // Also skip the token
        return new ParserInput(this.text.substring(oldOffset, tokenStart));
    }

    /**
     * Consumes characters between offset and given end index and makes
     * a plain text token of them.
     * @param end Absolute end index.
     */
    textToken(end: number): TextToken {
        const content = this.text.substring(this._offset, end);
        this._offset = end;
        return {type: 'text', content: [], value: content};
    }
}

function parseStyleToken(input: ParserInput, start: string): StyleToken {
    // Find matching end token and consume text until it
    input.discard(start.length);
    let content = input.consumeUntil(start) ?? input; // Default to end of input
    return {type: 'style', style: start == '**' ? 'strong' : 'em', content: parse(content)}
}

function parseLinkToken(input: ParserInput): PassageLinkToken {
    input.discard(1);
    const title = input.consumeUntil(']');
    if (!title) {
        throw new Error('invalid link title');
    }
    input.discard(1);
    const address = input.consumeUntil(')');
    if (!address) {
        throw new Error('invalid link address');
    }
    return {type: 'passage', content: parse(title), address: address.text};
}

/**
 * Escapes HTML special characters. This is mostly to prevent unintentional
 * formatting, we use DOMPurify for XSS protection.
 * @param input Untrusted input.
 */
export function htmlEscape(input: string): string {
    return input.replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

/**
 * Parses input into tokens. Note that paragraphs are not handled here.
 * @param input Parser input.
 */
export function parse(input: ParserInput | string): Token[] {
    if (typeof input == 'string') {
        input = new ParserInput(htmlEscape(input));
    }
    // Iterate characters that have not yet been consumed
    const tokens: Token[] = [];
    for (let i = input.offset; i < input.end;) {
        const c = input.text[i];
        switch (c) {
            case '*': // Italic or bold
                if (i > input.offset) {
                    tokens.push(input.textToken(i));
                }
                tokens.push(parseStyleToken(input, input.text[i + 1] == '*' ? '**' : '*'))
                i = input.offset;
                break;
            case '[': // Passage (link to a place)
                if (i > input.offset) {
                    tokens.push(input.textToken(i));
                }
                tokens.push(parseLinkToken(input));
                i = input.offset;
                break;
            default:
                i++; // Did not encounter token start, advance to next character
        }
    }
    if (input.offset != input.end) {
        tokens.push(input.textToken(input.end));
    }
    return tokens;
}

/**
 * Parses input into paragraph tokens that contain other tokens.
 * @param input Parser input.
 */
export function parseDocument(input: ParserInput | string): ParagraphToken[] {
    if (typeof input == 'string') {
        input = new ParserInput(htmlEscape(input));
    }
    const paragrapgs: ParagraphToken[] = [];
    while (true) {
        const p = input.consumeUntil('\n\n');
        // Parse until next paragraph, or to end for the last one
        const content = p ? parse(p) : parse(input);
        paragrapgs.push({type: 'paragraph', content: content});
        if (!p) {
            break;
        }
    }
    return paragrapgs;
}

function renderToken(token: Token): string {
    switch (token.type) {
        case 'text':
            return (token as TextToken).value;
        case 'paragraph':
            return `<p>${render(token.content)}</p>`
        case 'style':
            const style = token as StyleToken;
            switch (style.style) {
                case 'em':
                    return `<em>${render(style.content)}</em>`
                case 'strong':
                    return `<strong>${render(style.content)}</strong>`
            }
        case 'passage':
            const passage = token as PassageLinkToken;
            return `<a href="javascript:void" passage-to="${passage.address}>${render(passage.content)}</a>"`
        default:
            throw new Error(`unknown token type ${token.type}`);
    }
}

function render(tokens: Token[]): string {
    return tokens.map(token => renderToken(token)).join('');
}

export function renderHtml(tokens: Token[]): string {
    // Even though user-supplied HTML tags are escaped, WE are generating HTML
    // Sanitize it just in case something important was missed
    return DOMPurify.sanitize(render(tokens));
}

export function renderText(text: string): string {
    return DOMPurify.sanitize(htmlEscape(text));
}