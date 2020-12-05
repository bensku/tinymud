import { htmlEscape, parse, parseDocument, ParserInput } from "./render";

test('Basic parsing', () => {
    expect(parse(new ParserInput(''))).toEqual([]); // Empty input
    expect(parse(new ParserInput('Hello, World!')))
        .toEqual([{type: 'text', content: [], value: 'Hello, World!'}]);
});

test('Parsing styles', () => {
    // Basic style parsing
    expect(parse('*text*'))
        .toEqual([{type: 'style', style: 'em', content:
        [{type: 'text', content: [], value: 'text'}]}]);
    expect(parse('**text**'))
        .toEqual([{type: 'style', style: 'strong', content:
        [{type: 'text', content: [], value: 'text'}]}]);

    // Multiple styles and text
    // Not supporting mixing em+strong at same time is intentional
    expect(parse('**bold** of *you* to assume...')).toEqual([
        {type: 'style', style: 'strong', content: [{type: 'text', content: [], value: 'bold'}]},
        {type: 'text', content: [], value: ' of '},
        {type: 'style', style: 'em', content: [{type: 'text', content: [], value: 'you'}]},
        {type: 'text', content: [], value: ' to assume...'}
    ]);
    expect(parse('**hello** *world*')).toEqual([
        {type: 'style', style: 'strong', content: [{type: 'text', content: [], value: 'hello'}]},
        {type: 'text', content: [], value: ' '},
        {type: 'style', style: 'em', content: [{type: 'text', content: [], value: 'world'}]},
    ]);
    expect(parse('**hello***world*')).toEqual([
        {type: 'style', style: 'strong', content: [{type: 'text', content: [], value: 'hello'}]},
        {type: 'style', style: 'em', content: [{type: 'text', content: [], value: 'world'}]},
    ]);
});

test('Parsing passage links', () => {
    expect(parse('[Hey, you...](tutorial.awake)')).toEqual([
        {type: 'passage', address: 'tutorial.awake', content: [{type: 'text', content: [], value: 'Hey, you...'}]}
    ]);
    // Then with a little formatting inside
    expect(parse('are [finally *awake*!](tutorial.awake2)')).toEqual([
        {type: 'text', content: [], value: 'are '},
        {type: 'passage', address: 'tutorial.awake2', content: [
            {type: 'text', content: [], value: 'finally '},
            {type: 'style', style: 'em', content: [{type: 'text', content: [], value: 'awake'}]},
            {type: 'text', content: [], value: '!'},
        ]}
    ]);
});

test('Parsing documents with paragraphs', () => {
    expect(parseDocument('Hello\n\nWorld!')).toEqual([
        {type: 'paragraph', content: [{type: 'text', content: [], value: 'Hello'}]},
        {type: 'paragraph', content: [{type: 'text', content: [], value: 'World!'}]}
    ]);
    // Line break should not create a paragraph
    expect(parseDocument('Hello\nWorld!')).toEqual([
        {type: 'paragraph', content: [{type: 'text', content: [], value: 'Hello\nWorld!'}]}
    ]);
});

test('Escaping HTML', () => {
    const escaped = htmlEscape('<script>0 && 1</script>');
    expect(escaped).not.toContain('&&');
    expect(escaped).not.toContain('<');
    expect(escaped).not.toContain('>');
});

// TODO test rendering?