import { authenticate, AuthFailure } from "./auth";
import { prepareGame } from "./game/main";
import { changePage } from "./pages";
import { parseDocument, renderHtml, renderText } from "./render";

interface IntroResponse {
    title: string;
    header: string;
}

export async function loginPageHandler() {
    const userField = document.getElementById('user-field') as HTMLInputElement;
    const passwordField = document.getElementById('password-field') as HTMLInputElement;

    // Activate login and register buttons
    document.getElementById('login-form')!.addEventListener('submit', async (event) => {
        event.preventDefault();
        const result = await authenticate(userField.value, passwordField.value);
        if (result instanceof AuthFailure) {
            alert('Authentication failed.'); // TODO improve error
        } else {
            await prepareGame();
        }
    });

    document.getElementById('register-link')!.addEventListener('click', async (event) => {
        event.preventDefault();
        await changePage('register');
    });

    // Fetch game intro from server
    const intro: IntroResponse = await (await fetch(`game/intro`)).json();
    document.getElementById('intro-title')!.innerHTML = renderHtml(parseDocument(intro.title));
    document.getElementById('intro-content')!.innerHTML = renderText(intro.header);
}
