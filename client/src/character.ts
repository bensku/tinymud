import { changePage } from "./pages";
import { GameSocket } from "./socket";

export async function createCharacter(ws: GameSocket, options: string[]) {
    await changePage('character-create'); // Go to page where the elements are

    // Append templates we received from server
    const templates = document.getElementById('character-templates')!;
    for (let i = 0; i < options.length; i++) {
        templates.insertAdjacentHTML('beforeend', `<label><input type="radio" name="template" id="option-${i}" option-index="${i}" required>${options[i]}</label`);
    }

    // Bind create character button
    const characterName = document.getElementById('name-field') as HTMLInputElement;
    document.getElementById('create-button')!.addEventListener('click', async (event) => {
        const choice = document.querySelector('input[name=template]:checked');
        if (!choice) {
            return; // User didn't choose template for character yet
        }

        // Ready to create character
        const name = characterName.value;
        const index = parseInt(choice.getAttribute('option-index')!);

        await changePage('game'); // Open game to not miss place/character messages
        // Tell server our character name and index of template we chose
        ws.send({type: 'PickCharacterTemplate', name: name, selected: index});
    });
}