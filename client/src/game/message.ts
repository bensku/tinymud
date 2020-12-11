import { UserRoles } from "./main";
import { ClientMessage, ServerMessage } from "../socket";

/**
 * An object we can show to player.
 */
interface VisibleObj {
    id: number;
    name: string;
}

export interface ClientConfig extends ServerMessage {
    roles: UserRoles;
}

export interface UpdatePlace extends ServerMessage {
    address: string;
    title?: string;
    header?: string;
    passages?: PassageData[];
    characters?: VisibleObj[];
    items?: VisibleObj[];
}

export interface UpdateCharacter extends ServerMessage {
    character: VisibleObj;
    inventory?: VisibleObj[];
}

export interface CreateCharacter extends ServerMessage {
    options: string[];
}

export interface DisplayAlert extends ServerMessage {
    alert: string;
}

export interface PickCharacterTemplate extends ClientMessage {
    name: string;
    selected: number
}

export interface UsePassage extends ClientMessage {
    address: string;
}

export interface EditorTeleport extends ClientMessage {
    character: number;
    address: string;
}

export interface PassageData {
    address: string;
    name?: string;
    hidden: boolean;
}

export interface EditorPlaceEdit extends ClientMessage {
    address: string;
    title: string;
    header: string;
    passages: PassageData[]
}

export interface EditorPlaceCreate extends ClientMessage {
    address: string;
}

export interface EditorPlaceDestroy extends ClientMessage {
    address: string;
}