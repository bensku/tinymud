import { authenticate, AuthFailure } from "./auth";
import { prepareGame } from "./game";
import { changePage } from "./pages";

export async function loginPageHandler() {
    const userField = document.getElementById('user-field') as HTMLInputElement;
    const passwordField = document.getElementById('password-field') as HTMLInputElement;
    document.getElementById('login-button')!.addEventListener('click', async (event) => {
        const result = await authenticate(userField.value, passwordField.value);
        if (result instanceof AuthFailure) {
            alert('Authentication failed.'); // TODO improve error
        } else {
            await prepareGame();
        }
    });
}
