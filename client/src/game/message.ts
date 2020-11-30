import { ClientMessage, ServerMessage } from "../socket";

/**
 * An object we can show to player.
 */
interface VisibleObj {
    name: string;
}

export interface UpdatePlace extends ServerMessage {
    title?: string;
    header?: string;
    passages?: Record<number, string>;
    characters?: VisibleObj[];
    items?: VisibleObj[];
}

export interface UpdateCharacter extends ServerMessage {
    name?: string;
    inventory?: VisibleObj[];
}

export interface CreateCharacter extends ServerMessage {
    options: string[];
}

export interface PickCharacterTemplate extends ClientMessage {
    name: string;
    selected: number
}
