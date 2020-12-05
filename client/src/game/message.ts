import { UserRoles } from "./main";
import { ClientMessage, ServerMessage } from "../socket";

/**
 * An object we can show to player.
 */
interface VisibleObj {
    name: string;
}

export interface ClientConfig extends ServerMessage {
    roles: UserRoles;
}

export interface UpdatePlace extends ServerMessage {
    address: string;
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

export interface PlaceEditMessage extends ClientMessage {
    address: string;
    title: string;
    header: string;
}

export interface PlaceCreateMessage extends ClientMessage {
    address: string;
}

export interface PlaceDestroyMessage extends ClientMessage {
    address: string;
}