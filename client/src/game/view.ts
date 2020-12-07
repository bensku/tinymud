import CodeMirror from 'codemirror';
import { PassageLinkToken, parseDocument, renderHtml, renderText, visit } from "../render";
import { GameSocket } from '../socket';
import { UserRoles } from './main';
import { ClientConfig, EditorPlaceCreate, EditorPlaceDestroy, EditorPlaceEdit, EditorTeleport, PassageData, UpdateCharacter, UpdatePlace } from "./message";

class Character {
    id: number = -1;
    characterName = document.getElementById('char-name')!;
}

class Place {
    title = document.getElementById('place-title')!;
    header = document.getElementById('place-header')!;
    passages = document.getElementById('place-passages')!;

    /**
     * Header source code, not rendered to HTML.
     */
    headerText: string = '';
}

class PlaceEditor {
    createButton = document.getElementById('place-create-button')!;
    deleteButton = document.getElementById('place-delete-button')!;
    editButton = document.getElementById('place-edit-button')!;
    saveButton = document.getElementById('place-save-button')!;
    address = document.getElementById('place-address')!;

    headerEditor: CodeMirror.Editor | undefined;
    createPlace: boolean = false;

    display(): void {
        document.getElementById('place-editor')!.style.display = 'block';
    }

    enable(place: Place, create: boolean): void {
        // If we're creating a new place, allow editing address
        let titleText;
        let headerText;
        if (create) {
            this.createPlace = true;
            this.address.outerHTML = `<input id="place-address" type="text" placeholder="place.address">`;
            this.address = document.getElementById('place-address')!;

            // Also don't pre-fill title or header
            titleText = '';
            headerText = '';
        } else {
            // Pre-fill with current content
            titleText = renderText(place.title.innerText);
            headerText = renderText(place.headerText);
        }

        // Make title editable
        place.title.outerHTML = `<input id="place-title" type="text" value="${titleText}">`;
        place.title = document.getElementById('place-title')!;

        // Replace header with CodeMirror editor
        place.header.innerHTML = ''; // This would display above CodeMirror
        this.headerEditor = CodeMirror(place.header, {
            value: headerText,
            lineWrapping: true
            //mode: 'markdown' // TODO tinymud format is not exactly markdown
            // ... should define a custom grammar instead
            // TODO markdown doesn't work, issues with bundler
        });

        // Swap edit with save button
        this.editButton.style.display = 'none';
        this.saveButton.style.display = 'inline-block';
    }

    finish(place: Place, character: Character, ws: GameSocket): void {
        if (this.createPlace) {
            const address = (this.address as HTMLInputElement).value;
            if (address == '') {
                alert('Place address needed.');
                return;
            }
            // Swap back normal address element
            this.address.outerHTML = `<code id="place-address">${address}</code>`;
            this.address = document.getElementById('place-address')!;
            
            // Create empty place, we'll update the content later
            const createMsg: EditorPlaceCreate = {
                type: 'EditorPlaceCreate',
                address: address
            };
            ws.send(createMsg);
            this.createPlace = false; // Until we create another place

            // Move ourself to the new place
            const teleportMsg: EditorTeleport = {
                type: 'EditorTeleport',
                character: character.id,
                address: address
            }
            ws.send(teleportMsg);
        }

        // Collect changes from input fields
        const title = (place.title as HTMLInputElement).value;
        const header = this.headerEditor!.getValue();
        const headerTokens = parseDocument(header);
        const headerHtml = renderHtml(headerTokens);

        // Replace input input fields with original elements
        // TODO don't duplicate code with game.html AND updatePlace()
        place.title.outerHTML = `<h1 id="place-title">${renderText(title)}</h1>`;
        place.title = document.getElementById('place-title')!;
        this.headerEditor = undefined; // We'll make new one if this is edited again
        place.header.outerHTML = `<section id="place-header">${headerHtml}</section>`;
        place.header = document.getElementById('place-header')!;
        place.headerText = header; // In case this is edited again

        // Compute passages by visiting parsed header tokens
        const passages: PassageData[] = [];
        visit(headerTokens, (token) => {
            if (token.type == 'passage') {
                const link = token as PassageLinkToken;
                // TODO name/hidden support
                passages.push({address: link.address, name: undefined, hidden: false});
            }
        });

        // Tell the server about changes
        const msg: EditorPlaceEdit = {
            type: 'EditorPlaceEdit',
            address: this.address.innerText,
            title: title,
            header: header,
            passages: passages
        };
        ws.send(msg);

        // Swap edit button back
        this.editButton.style.display = 'inline-block';
        this.saveButton.style.display = 'none';
    }

    delete(place: Place, ws: GameSocket): void {
        if (!confirm(`Deleting place '${place.title.innerText}. Are you sure?'`)) {
            return; // User canceled
        }
        const msg: EditorPlaceDestroy = {
            type: 'EditorPlaceDestroy',
            address: this.address.innerText
        }
        ws.send(msg);
    }
}

export class GameView {
    private config: ClientConfig;

    private character;
    private place;
    private editor: PlaceEditor | undefined;

    constructor(config: ClientConfig, ws: GameSocket) {
        this.config = config;
        this.character = new Character();
        this.place = new Place();

        // Enable editor functionality only for... editors
        if ((config.roles & UserRoles.EDITOR) != 0) {
            const editor = new PlaceEditor();
            this.editor = editor;
            editor.display();

            // Both edit and save buttons are never visible simultaneously
            editor.editButton.addEventListener('click', (event) => editor.enable(this.place, false));
            editor.saveButton.addEventListener('click', (event) => editor.finish(this.place, this.character, ws));

            editor.createButton.addEventListener('click', (event) => editor.enable(this.place, true));
            editor.deleteButton.addEventListener('click', (event) => editor.delete(this.place, ws));
        }
    }

    updatePlace(msg: UpdatePlace) {
        if (this.editor) {
            this.editor.address.innerText = renderText(msg.address);
        }
        if (msg.title) {
            this.place.title.innerText = renderText(msg.title);
        }
        if (msg.header) {
            this.place.headerText = msg.header; // For editing with CodeMirror only
            // Render to safe HTML
            this.place.header.innerHTML = renderHtml(parseDocument(msg.header));
        }
    }

    updateCharacter(msg: UpdateCharacter) {
        this.character.id = msg.character.id;
        this.character.characterName.innerText = renderText(msg.character.name);
    }
}