import { createCharacter } from "../character";
import { BACKEND_URL } from "../common";
import { GameView } from "./view";
import { changePage } from "../pages";
import { ClientMessage, GameSocket, openGameSocket, ServerMessage } from "../socket";
import { CreateCharacter } from "./message";

let view: GameView;
let ws: GameSocket;

async function handleReceivedMsg(msg: ServerMessage) {
    switch (msg.type) {
        case 'UpdatePlace':
            view.updatePlace(msg);
            break;
        case 'UpdateCharacter':
            view.updateCharacter(msg);
            break;
    }
}

async function runGame() {
    await changePage('game'); // In case we weren't there yet
    // Loop forever, handling messages from server
    while (true) {
        await handleReceivedMsg(await ws.receive());
    }
}

export async function prepareGame() {
    ws = await openGameSocket(); // This logs in (with token, should always succeed)

    // Wait for first message to see if we need to
    // - create a character
    // - select a character (when that is supported)
    const msg = await ws.receive();
    switch (msg.type) {
        case 'CreateCharacter':
            await createCharacter(ws, (msg as CreateCharacter).options);
            break;
            // TODO character select
        default:
            await changePage('game'); // Before handling received message!
            await handleReceivedMsg(msg); // Handle message, whatever it was
            await runGame(); // Ready to run game
    }
}

export async function gamePageHandler() {
    view = new GameView(); // Now that page has the needed elements
}