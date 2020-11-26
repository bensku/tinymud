import jwtDecode from "../node_modules/jwt-decode/index";
import { BACKEND_URL } from "./common";

interface LoginRequest {
    name: string;
    password: string;
};

export class AuthFailure {
    readonly httpStatus: number;

    constructor(httpStatus: number) {
        this.httpStatus = httpStatus;
    }
}

async function requestToken(request: LoginRequest): Promise<string | AuthFailure> {
    const response = await fetch(BACKEND_URL + 'auth/login', {
        method: 'POST',
        body: JSON.stringify(request)
    });
    if (response.status != 200) {
        return new AuthFailure(response.status);
    }
    return response.text();
}

/**
 * Requests a new authentication token with current token.
 * @param token Current token.
 */
async function requestRenew(token: string): Promise<string | AuthFailure> {
    const response = await fetch(BACKEND_URL + 'auth/renew', {
        method: 'POST',
        body: JSON.stringify(token)
    });
    if (response.status != 200) {
        return new AuthFailure(response.status);
    }
    return response.text();
}

/**
 * Gets the current authentication token.
 */
export function getAuthToken(): string | null {
    return localStorage.getItem('tinymud-token');
}

/**
 * Renews current authentication token if it would expire soon.
 */
export async function renewAuthToken(): Promise<boolean | AuthFailure> {
    const token = getAuthToken();
    if (token == null) {
        return new AuthFailure(401);
    }
    const result = await requestRenew(token);
    if (result instanceof AuthFailure) {
        return result; // We have token, but is didn't work
    } else { // Got new token, save to local storage
        localStorage.setItem('tinymud-token', result);
        return true;
    }
}

export async function authenticate(user: string, password: string): Promise<boolean | AuthFailure> {
    const request: LoginRequest = {
        name: user,
        password: password
    };
    const result = await requestToken(request);
    if (result instanceof AuthFailure) {
        return result; // Authentication failed, probably bad credentials
    }

    // Success, let's store the token
    localStorage.setItem('tinymud-token', result);
    return true;
}