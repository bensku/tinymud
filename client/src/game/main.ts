import { createCharacter } from "../character";
import { GameView } from "./view";
import { changePage } from "../pages";
import { GameSocket, openGameSocket, ServerMessage } from "../socket";
import { ClientConfig, CreateCharacter, DisplayAlert, UpdateCharacter, UpdatePlace } from "./message";

let config: ClientConfig;
let view: GameView;
let ws: GameSocket;

/**
 * User roles, sent by backend in a bit set.
 */
export enum UserRoles {
    PLAYER = 1,
    EDITOR = 2
}

async function handleReceivedMsg(msg: ServerMessage) {
    switch (msg.type) {
        case 'UpdatePlace':
            view.updatePlace(msg as UpdatePlace);
            break;
        case 'UpdateCharacter':
            view.updateCharacter(msg as UpdateCharacter);
            break;
        case 'DisplayAlert':
            alert((msg as DisplayAlert).alert);
            break;
        default:
            console.log(`Warning: unknown message type ${msg.type}`);
    }
}

export async function runGame() {
    await changePage('game'); // In case we weren't there yet
    // Loop forever, handling messages from server
    while (true) {
        try {
            await handleReceivedMsg(await ws.receive());
        } catch (e) {
            console.log('Websocket disconnected, reloading...');
            location.reload(); // TODO can we do this without full reload?
        }
    }
}

export async function prepareGame() {
    ws = await openGameSocket(); // This logs in (with token, should always succeed)

    // Receive client configuration from server
    config = await ws.receive('ClientConfig');

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
    view = new GameView(config, ws); // Now that page has the needed elements
}