import { AuthFailure, renewAuthToken } from "./auth";
import { gamePageHandler } from "./game";
import { loginPageHandler } from "./login";
import { changePage, registerPage } from "./pages";


// Register pages
registerPage('login', loginPageHandler);
registerPage('game', gamePageHandler);


// Initialize Tinymud client (async needed, no callbacks wanted here)
window.onload = async () => {
    const result = await renewAuthToken();
    if (result instanceof AuthFailure) { // Missing or outdated token
        changePage('login');
    } else { // We have valid auth token, skip login...
        changePage('game');
    }
}