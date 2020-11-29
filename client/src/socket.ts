import { getAuthToken } from "./auth";
import { BACKEND_URL, GAME_WS_URL } from "./common";

interface PromiseCompleter<T> {
    resolve: (value: T | PromiseLike<T>) => void;
    reject: (reason?: any) => void;
}

/**
 * Connects a WebSocket wrapper with async support.
 */
export async function openAsyncSocket(url: string): Promise<AsyncSocket> {
    const ws = new WebSocket(url);  // Start opening the socket

    // Make a promise that will resolve to WebSocket when it has opened
    const completer: Partial<PromiseCompleter<WebSocket>> = {};
    const promise = new Promise((resolve, reject) => {
        completer.resolve = resolve;
        completer.reject = reject;
    });
    ws.addEventListener('open', (event: Event) => {
        completer.resolve!(ws);
    });
    
    await promise; // Wait on the promise
    return new AsyncSocket(ws);
}

export class AsyncSocket {
    /**
     * The underlying websocket.
     */
    private ws: WebSocket;

    /**
     * Received messages and events that did not have promises
     * waiting for them.
     */
    private events: any[];

    /**
     * Promises waiting to get messages and events.
     */
    private receivers: PromiseCompleter<string>[];

    constructor(ws: WebSocket) {
        this.ws = this.listenSocket(ws);
        this.events = [];
        this.receivers = [];
    }

    private handleEvent(data: any, fail: boolean) {
        const receiver = this.receivers.shift();
        if (!receiver) {
            // No one wants this now, but maybe later...
            this.events.push(data);
        } else {
            // Trigger the receiver as success or as failure
            if (fail) {
                receiver.reject(data);
            } else {
                receiver.resolve(data);
            }
        }
    }

    private listenSocket(ws: WebSocket): WebSocket {
        ws.addEventListener('error', (event) => this.handleEvent(event, true));
        ws.addEventListener('message', (event) => this.handleEvent(event.data, false));
        ws.addEventListener('close', (event) => this.handleEvent(event, true));
        return ws;
    }

    send(msg: string): void {
        this.ws.send(msg);
    }

    receive(): Promise<string> {
        return new Promise((resolve, reject) => {
            const event = this.events.shift();
            if (!event) {
                // Nothing available, we'll wait in queue
                this.receivers.push({resolve: resolve, reject: reject});
            } else {
                // Immediately trigger the promise
                if (typeof event == 'string') {
                    resolve(event); // Looks like we didn't get an error
                } else {
                    reject(event); // Error, hopefully
                }
            }
        });
    }
}

interface GameMessage {
    type: string;
}

/**
 * Message from server to client.
 */
export interface ServerMessage extends GameMessage {}

/**
 * Message from client to server.
 */
export interface ClientMessage extends GameMessage {}

/**
 * Opens a game socket and logs in with current token.
 */
export async function openGameSocket(): Promise<GameSocket> {
    const authToken = getAuthToken();
    if (!authToken) {
        throw new Error("missing auth token, are we logged in?");
    }
    const ws = await openAsyncSocket(GAME_WS_URL);
    ws.send(authToken); // Log in with the token
    // TODO should validate the token or handle errors...
    return new GameSocket(ws);
}

export class GameSocket {
    /**
     * Backing socket.
     */
    private socket: AsyncSocket;

    /**
     * Use openGameSocket() instead. It handles login automatically!
     * @param socket Backing socket.
     */
    constructor(socket: AsyncSocket) {
        this.socket = socket;
    }

    send<T extends ClientMessage>(msg: T) {
        this.socket.send(JSON.stringify(msg));
    }

    async receive(type?: string): Promise<ServerMessage> {
        const msg: ServerMessage = JSON.parse(await this.socket.receive());
        if (type && msg.type != type) {
            throw new Error(`expected message type ${type}, but got ${msg.type}`)
        }
        return msg;
    }
}