import { UpdateCharacter, UpdatePlace } from "./message";

class Sidebar {
    characterName = document.getElementById('char-name')!;
}

class Place {
    title = document.getElementById('place-title')!;
    area = document.getElementById('place-area')!;
    header = document.getElementById('place-header')!;
    passages = document.getElementById('place-passages')!;
}

export class GameView {
    private sidebar = new Sidebar();
    private place = new Place();

    updatePlace(msg: UpdatePlace) {
        if (msg.title) {
            this.place.title.innerText = msg.title;
        }
        if (msg.header) {
            this.place.header.innerText = msg.header;
        }
    }

    updateCharacter(msg: UpdateCharacter) {
        if (msg.name) {
            this.sidebar.characterName.innerText = msg.name;
        }
    }
}