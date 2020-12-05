import CodeMirror from 'codemirror';
import { parseDocument, renderHtml, renderText } from "../render";
import { GameSocket } from '../socket';
import { UserRoles } from './main';
import { ClientConfig, PlaceEditMessage, UpdateCharacter, UpdatePlace } from "./message";

class Sidebar {
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
    address = document.getElementById('place-address')!;
    editButton = document.getElementById('place-edit-button')!;
    saveButton = document.getElementById('place-save-button')!;

    headerEditor: CodeMirror.Editor | undefined;

    display(): void {
        document.getElementById('place-editor')!.style.display = 'block';
    }

    enable(place: Place): void {
        // Make title editable
        const titleText = renderText(place.title.innerText);
        place.title.outerHTML = `<input id="place-title" type="text" value="${titleText}">`;
        place.title = document.getElementById('place-title')!;

        // Replace header with CodeMirror editor
        place.header.innerHTML = '';
        const headerText = renderText(place.headerText);
        this.headerEditor = CodeMirror(place.header, {
            value: headerText
            //mode: 'markdown' // TODO tinymud format is not exactly markdown
            // ... should define a custom grammar instead
        });
        // TODO codemirror styles

        // Swap edit with save button
        this.editButton.style.display = 'none';
        this.saveButton.style.display = 'inline-block';
    }

    async finish(place: Place, ws: GameSocket): Promise<void> {
        // Collect changes from input fields
        const title = (place.title as HTMLInputElement).value;
        const header = this.headerEditor!.getValue();
        const headerHtml = renderHtml(parseDocument(header));

        // Replace input input fields with original elements
        // TODO don't duplicate code with game.html AND updatePlace()
        place.title.outerHTML = `<h1 id="place-title">${renderText(title)}</h1>`;
        place.title = document.getElementById('place-title')!;
        this.headerEditor = undefined; // We'll make new one if this is edited again
        place.header.outerHTML = `<section id="place-header">${headerHtml}</section>`;
        place.header = document.getElementById('place-header')!;
        place.headerText = header; // In case this is edited again

        // Tell the server about changes
        const msg: PlaceEditMessage = {
            type: 'PlaceEditMessage',
            address: this.address.innerText,
            title: title,
            header: header
        }
        await ws.send(msg);

        // Swap edit button back
        this.editButton.style.display = 'inline-block';
        this.saveButton.style.display = 'none';
    }
}

export class GameView {
    private config: ClientConfig;

    private sidebar;
    private place;
    private editor: PlaceEditor | undefined;

    constructor(config: ClientConfig, ws: GameSocket) {
        this.config = config;
        this.sidebar = new Sidebar();
        this.place = new Place();

        // Enable editor functionality only for... editors
        if ((config.roles & UserRoles.EDITOR) == 0) {
            const editor = new PlaceEditor();
            this.editor = editor;
            editor.display();

            // Both edit and save buttons are never visible simultaneously
            editor.editButton.addEventListener('click', (event) => editor.enable(this.place));
            editor.saveButton.addEventListener('click', async (event) => await editor.finish(this.place, ws));
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
        if (msg.name) {
            this.sidebar.characterName.innerText = msg.name;
        }
    }
}